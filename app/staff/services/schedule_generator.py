from datetime import date, time, timedelta, datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func

from app.core.exceptions import ValidationError, BusinessLogicError
from app.staff.models.groups import Group
from app.staff.models.lessons import Lesson
from app.staff.schemas.schedule import ScheduleTemplate, GenerateLessonsRequest


class ScheduleGenerator:
    """Сервис для генерации занятий из шаблона расписания"""

    # Общеизвестные праздники Казахстана (можно расширить)
    DEFAULT_HOLIDAYS = {
        (1, 1): "New Year",
        (1, 2): "New Year Holiday",
        (3, 8): "International Women's Day",
        (3, 21): "Nauryz",
        (3, 22): "Nauryz Holiday",
        (3, 23): "Nauryz Holiday",
        (5, 1): "Kazakhstan People's Unity Day",
        (5, 7): "Defender of the Fatherland Day",
        (5, 9): "Victory Day",
        (7, 6): "Capital City Day",
        (8, 30): "Constitution Day",
        (12, 1): "First President Day",
        (12, 16): "Independence Day",
        (12, 17): "Independence Day Holiday",
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_lessons_from_template(
        self, group_id: int, request: GenerateLessonsRequest
    ) -> Tuple[int, int, int]:
        """
        Генерирует занятия из шаблона расписания группы

        Returns:
            Tuple[generated_count, skipped_count, overwritten_count]
        """
        # Получаем группу с шаблоном расписания
        group = await self._get_group_with_schedule(group_id)

        if not group.schedule:
            raise BusinessLogicError("Group has no schedule template")

        # Парсим шаблон расписания
        try:
            schedule_template = ScheduleTemplate(**group.schedule)
        except Exception as e:
            raise ValidationError(f"Invalid schedule template format: {str(e)}")

        # Проверяем, что период генерации входит в действующий период шаблона
        self._validate_generation_period(schedule_template, request)

        # Получаем существующие занятия в периоде (если нужно проверить перезапись)
        existing_lessons = {}
        if not request.overwrite_existing:
            existing_lessons = await self._get_existing_lessons_map(
                group_id, request.start_date, request.end_date
            )

        # Генерируем занятия
        lessons_to_create = []
        skipped_count = 0
        overwritten_count = 0

        current_date = request.start_date
        while current_date <= request.end_date:
            # Проверяем, есть ли занятия в этот день по шаблону
            weekday_lessons = self._get_weekday_lessons(schedule_template, current_date)

            for lesson_time_slot in weekday_lessons:
                lesson_key = (current_date, lesson_time_slot["time"])

                # Проверяем праздники
                if request.exclude_holidays and self._is_holiday(current_date):
                    skipped_count += 1
                    continue

                # Проверяем существующие занятия
                if lesson_key in existing_lessons:
                    if request.overwrite_existing:
                        # Удаляем существующее занятие
                        await self._delete_lesson(existing_lessons[lesson_key])
                        overwritten_count += 1
                    else:
                        skipped_count += 1
                        continue

                # Создаем новое занятие
                lesson = self._create_lesson_from_template(
                    group, current_date, lesson_time_slot
                )
                lessons_to_create.append(lesson)

            current_date += timedelta(days=1)

        # Сохраняем все занятия batch'ом
        if lessons_to_create:
            self.session.add_all(lessons_to_create)
            await self.session.commit()

        return len(lessons_to_create), skipped_count, overwritten_count

    async def regenerate_lessons_for_period(
        self,
        group_id: int,
        start_date: date,
        end_date: date,
        preserve_modifications: bool = True,
    ) -> Tuple[int, int]:
        """
        Перегенерирует занятия для периода, сохраняя изменения

        Returns:
            Tuple[generated_count, preserved_count]
        """
        # Получаем группу
        group = await self._get_group_with_schedule(group_id)

        if not group.schedule:
            raise BusinessLogicError("Group has no schedule template")

        # Получаем существующие занятия
        existing_lessons = await self._get_existing_lessons_in_period(
            group_id, start_date, end_date
        )

        # Разделяем занятия на модифицированные и немодифицированные
        modified_lessons = []
        template_lessons = []

        for lesson in existing_lessons:
            if (
                lesson.status != "scheduled"
                or lesson.actual_date is not None
                or lesson.actual_start_time is not None
                or not lesson.created_from_template
            ):
                modified_lessons.append(lesson)
            else:
                template_lessons.append(lesson)

        # Удаляем только немодифицированные занятия
        for lesson in template_lessons:
            await self.session.delete(lesson)

        # Генерируем новые занятия
        request = GenerateLessonsRequest(
            start_date=start_date,
            end_date=end_date,
            overwrite_existing=False,  # Не перезаписываем модифицированные
        )

        generated_count, _, _ = await self.generate_lessons_from_template(
            group_id, request
        )

        return generated_count, len(modified_lessons)

    async def _get_group_with_schedule(self, group_id: int) -> Group:
        """Получает группу с проверкой существования"""
        result = await self.session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()

        if not group:
            raise ValidationError(f"Group with id {group_id} not found")

        return group

    def _validate_generation_period(
        self, schedule_template: ScheduleTemplate, request: GenerateLessonsRequest
    ):
        """Валидирует период генерации относительно шаблона"""
        if request.start_date < schedule_template.valid_from:
            raise ValidationError(
                f"Generation start date {request.start_date} is before template valid_from {schedule_template.valid_from}"
            )

        if request.end_date > schedule_template.valid_until:
            raise ValidationError(
                f"Generation end date {request.end_date} is after template valid_until {schedule_template.valid_until}"
            )

    async def _get_existing_lessons_map(
        self, group_id: int, start_date: date, end_date: date
    ) -> Dict[Tuple[date, time], int]:
        """Получает карту существующих занятий (дата, время) -> lesson_id"""
        result = await self.session.execute(
            select(Lesson.id, Lesson.planned_date, Lesson.planned_start_time).where(
                and_(
                    Lesson.group_id == group_id,
                    Lesson.planned_date >= start_date,
                    Lesson.planned_date <= end_date,
                )
            )
        )

        return {
            (lesson_date, lesson_time): lesson_id
            for lesson_id, lesson_date, lesson_time in result.fetchall()
        }

    async def _get_existing_lessons_in_period(
        self, group_id: int, start_date: date, end_date: date
    ) -> List[Lesson]:
        """Получает все существующие занятия в периоде"""
        result = await self.session.execute(
            select(Lesson).where(
                and_(
                    Lesson.group_id == group_id,
                    Lesson.planned_date >= start_date,
                    Lesson.planned_date <= end_date,
                )
            )
        )

        return result.scalars().all()

    async def _delete_lesson(self, lesson_id: int):
        """Удаляет занятие по ID"""
        result = await self.session.execute(
            select(Lesson).where(Lesson.id == lesson_id)
        )
        lesson = result.scalar_one_or_none()

        if lesson:
            await self.session.delete(lesson)

    def _get_weekday_lessons(
        self, schedule_template: ScheduleTemplate, date_obj: date
    ) -> List[Dict[str, Any]]:
        """Получает занятия для конкретного дня недели из шаблона"""
        weekday_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]

        weekday_name = weekday_names[date_obj.weekday()]
        weekday_schedule = getattr(schedule_template.weekly_pattern, weekday_name, [])

        return [
            {"time": time.fromisoformat(slot.time), "duration": slot.duration}
            for slot in weekday_schedule
        ]

    def _create_lesson_from_template(
        self, group: Group, lesson_date: date, time_slot: Dict[str, Any]
    ) -> Lesson:
        """Создает объект занятия из шаблона"""
        return Lesson(
            group_id=group.id,
            planned_date=lesson_date,
            planned_start_time=time_slot["time"],
            duration_minutes=time_slot["duration"],
            coach_id=group.coach_id,  # Берем тренера из группы
            status="scheduled",
            created_from_template=True,
        )

    def _is_holiday(self, date_obj: date) -> bool:
        """Проверяет, является ли дата праздником"""
        return (date_obj.month, date_obj.day) in self.DEFAULT_HOLIDAYS

    async def get_schedule_conflicts(
        self, coach_id: int, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Находит конфликты в расписании тренера
        (перекрывающиеся занятия)
        """
        result = await self.session.execute(
            select(
                Lesson.id,
                Lesson.planned_date,
                Lesson.planned_start_time,
                Lesson.duration_minutes,
                Lesson.group_id,
                Group.name.label("group_name"),
            )
            .join(Group, Lesson.group_id == Group.id)
            .where(
                and_(
                    Lesson.coach_id == coach_id,
                    Lesson.planned_date >= start_date,
                    Lesson.planned_date <= end_date,
                    Lesson.status == "scheduled",
                )
            )
            .order_by(Lesson.planned_date, Lesson.planned_start_time)
        )

        lessons = result.fetchall()
        conflicts = []

        # Группируем по дате
        lessons_by_date = {}
        for lesson in lessons:
            lesson_date = lesson.planned_date
            if lesson_date not in lessons_by_date:
                lessons_by_date[lesson_date] = []
            lessons_by_date[lesson_date].append(lesson)

        # Ищем пересечения в каждом дне
        for lesson_date, day_lessons in lessons_by_date.items():
            for i in range(len(day_lessons)):
                for j in range(i + 1, len(day_lessons)):
                    lesson1 = day_lessons[i]
                    lesson2 = day_lessons[j]

                    # Вычисляем время окончания первого занятия
                    end_time1 = (
                        datetime.combine(lesson_date, lesson1.planned_start_time)
                        + timedelta(minutes=lesson1.duration_minutes)
                    ).time()

                    # Проверяем пересечение
                    if lesson2.planned_start_time < end_time1:
                        conflicts.append(
                            {
                                "date": lesson_date,
                                "lesson1": {
                                    "id": lesson1.id,
                                    "group_name": lesson1.group_name,
                                    "start_time": lesson1.planned_start_time,
                                    "duration": lesson1.duration_minutes,
                                },
                                "lesson2": {
                                    "id": lesson2.id,
                                    "group_name": lesson2.group_name,
                                    "start_time": lesson2.planned_start_time,
                                    "duration": lesson2.duration_minutes,
                                },
                            }
                        )

        return conflicts


# Утилитарные функции для работы с расписанием
def calculate_lesson_end_time(start_time: time, duration_minutes: int) -> time:
    """Вычисляет время окончания занятия"""
    start_datetime = datetime.combine(date.today(), start_time)
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    return end_datetime.time()


def get_week_date_range(date_obj: date) -> Tuple[date, date]:
    """Получает начало и конец недели для заданной даты"""
    # Понедельник - начало недели
    days_since_monday = date_obj.weekday()
    week_start = date_obj - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_month_date_range(year: int, month: int) -> Tuple[date, date]:
    """Получает начало и конец месяца"""
    month_start = date(year, month, 1)

    # Находим последний день месяца
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    month_end = next_month_start - timedelta(days=1)
    return month_start, month_end
