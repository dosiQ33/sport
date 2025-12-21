"""Student Clubs CRUD - Operations for viewing available clubs"""

import math
from typing import List, Tuple, Optional
from sqlalchemy import and_, or_, func, text
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import db_operation
from app.core.exceptions import NotFoundError
from app.staff.models.clubs import Club
from app.staff.models.sections import Section
from app.staff.models.groups import Group
from app.staff.models.tariffs import Tariff
from app.staff.models.enrollments import StudentEnrollment, EnrollmentStatus
from app.staff.models.users import UserStaff
from app.staff.models.section_coaches import SectionCoach
from app.students.schemas.clubs import (
    ClubRead,
    ClubDetailRead,
    ClubSectionRead,
    ClubTariffRead,
    ClubCoachRead,
    ClubLocationRead,
    NearestClubResponse,
    TariffAccessInfo,
)


@db_operation
async def get_clubs_list(
    session: AsyncSession,
    student_id: int,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    only_my_clubs: bool = False,
) -> Tuple[List[ClubRead], int]:
    """Get list of clubs"""
    # Get student's enrolled club IDs
    enrollment_query = (
        select(Section.club_id)
        .select_from(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(StudentEnrollment.student_id == student_id)
    )
    enrollment_result = await session.execute(enrollment_query)
    enrolled_club_ids = list(set([row[0] for row in enrollment_result.fetchall()]))

    # Build base query
    base_query = select(Club)

    if only_my_clubs:
        if not enrolled_club_ids:
            return [], 0
        base_query = base_query.where(Club.id.in_(enrolled_club_ids))

    if search:
        search_term = f"%{search.strip()}%"
        base_query = base_query.where(
            or_(Club.name.ilike(search_term), Club.description.ilike(search_term))
        )

    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    query = base_query.order_by(Club.name.asc()).offset(skip).limit(limit)
    result = await session.execute(query)
    clubs_data = result.scalars().all()

    clubs = []
    for club in clubs_data:
        # Count sections
        sections_query = select(func.count(Section.id)).where(
            Section.club_id == club.id
        )
        sections_result = await session.execute(sections_query)
        sections_count = sections_result.scalar() or 0

        # Count students (unique enrollments)
        students_query = (
            select(func.count(func.distinct(StudentEnrollment.student_id)))
            .select_from(StudentEnrollment)
            .join(Group, StudentEnrollment.group_id == Group.id)
            .join(Section, Group.section_id == Section.id)
            .where(
                and_(
                    Section.club_id == club.id,
                    StudentEnrollment.status.in_(
                        [EnrollmentStatus.active, EnrollmentStatus.new]
                    ),
                )
            )
        )
        students_result = await session.execute(students_query)
        students_count = students_result.scalar() or 0

        clubs.append(
            ClubRead(
                id=club.id,
                name=club.name,
                description=club.description,
                city=club.city,
                address=club.address,
                logo_url=club.logo_url,
                cover_url=club.cover_url,
                phone=club.phone,
                telegram_url=club.telegram_url,
                instagram_url=club.instagram_url,
                whatsapp_url=club.whatsapp_url,
                working_hours=club.working_hours,
                sections_count=sections_count,
                students_count=students_count,
                tags=club.tags or [],
            )
        )

    return clubs, total


@db_operation
async def get_club_details(session: AsyncSession, club_id: int) -> ClubDetailRead:
    """Get detailed club information with sections, tariffs, and coaches"""
    # Get club
    club_query = select(Club).where(Club.id == club_id)
    club_result = await session.execute(club_query)
    club = club_result.scalar_one_or_none()

    if not club:
        raise NotFoundError("Club", str(club_id))

    # Get sections
    sections_query = (
        select(Section)
        .where(and_(Section.club_id == club_id, Section.active == True))
        .order_by(Section.name.asc())
    )
    sections_result = await session.execute(sections_query)
    sections_data = sections_result.scalars().all()

    sections = [
        ClubSectionRead(
            id=s.id,
            name=s.name,
            description=s.description,
        )
        for s in sections_data
    ]

    # Get coaches for this club (coaches from sections belonging to this club)
    # First get all section IDs for this club
    section_ids = [s.id for s in sections_data]
    
    coaches = []
    if section_ids:
        # Get coaches from section_coaches table
        # Only select specific columns to avoid JSON comparison issues with DISTINCT
        coaches_query = (
            select(
                UserStaff.id,
                UserStaff.first_name,
                UserStaff.last_name,
                UserStaff.photo_url,
                Section.name.label('section_name')
            )
            .select_from(SectionCoach)
            .join(UserStaff, SectionCoach.coach_id == UserStaff.id)
            .join(Section, SectionCoach.section_id == Section.id)
            .where(
                and_(
                    SectionCoach.section_id.in_(section_ids),
                    SectionCoach.is_active == True
                )
            )
        )
        coaches_result = await session.execute(coaches_query)
        coaches_rows = coaches_result.fetchall()
        
        # Also get primary coaches from sections (legacy relationship)
        primary_coaches_query = (
            select(
                UserStaff.id,
                UserStaff.first_name,
                UserStaff.last_name,
                UserStaff.photo_url,
                Section.name.label('section_name')
            )
            .select_from(Section)
            .join(UserStaff, Section.coach_id == UserStaff.id)
            .where(
                and_(
                    Section.club_id == club_id,
                    Section.active == True
                )
            )
        )
        primary_coaches_result = await session.execute(primary_coaches_query)
        primary_coaches_rows = primary_coaches_result.fetchall()
        
        # Combine and deduplicate coaches
        seen_coach_ids = set()
        for row in list(coaches_rows) + list(primary_coaches_rows):
            coach_id = row[0]
            first_name = row[1]
            last_name = row[2]
            photo_url = row[3]
            section_name = row[4]
            if coach_id not in seen_coach_ids:
                seen_coach_ids.add(coach_id)
                coaches.append(
                    ClubCoachRead(
                        id=coach_id,
                        first_name=first_name,
                        last_name=last_name,
                        photo_url=photo_url,
                        specialization=section_name,
                    )
                )

    tariffs_query = (
        select(Tariff)
        .where(
            and_(Tariff.club_ids.cast(JSONB).contains([club_id]), Tariff.active == True)
        )
        .order_by(Tariff.price.asc())
    )
    tariffs_result = await session.execute(tariffs_query)
    tariffs_data = tariffs_result.scalars().all()

    # Build lookups for section and group names
    section_names_map = {s.id: s.name for s in sections_data}
    
    # Fetch all groups for this club's sections (separate query to avoid lazy loading)
    groups_query = (
        select(Group)
        .where(Group.section_id.in_([s.id for s in sections_data]))
    )
    groups_result = await session.execute(groups_query)
    groups_data = groups_result.scalars().all()
    
    group_names_map = {g.id: g.name for g in groups_data}
    # Map section_id to list of groups
    section_groups_map = {}
    for g in groups_data:
        if g.section_id not in section_groups_map:
            section_groups_map[g.section_id] = []
        section_groups_map[g.section_id].append(g)

    # Map tariffs with resolved section/group names
    tariffs = []
    for t in tariffs_data:
        # Resolve section IDs to names
        included_sections = []
        tariff_section_ids = t.section_ids or []
        for sid in tariff_section_ids:
            if sid in section_names_map:
                included_sections.append(TariffAccessInfo(
                    id=sid,
                    name=section_names_map[sid],
                    type='section'
                ))
        
        # Resolve group IDs to names
        included_groups = []
        tariff_group_ids = t.group_ids or []
        for gid in tariff_group_ids:
            if gid in group_names_map:
                included_groups.append(TariffAccessInfo(
                    id=gid,
                    name=group_names_map[gid],
                    type='group'
                ))
        
        # For full_club type, include all sections
        if t.type == 'full_club':
            included_sections = [
                TariffAccessInfo(id=s.id, name=s.name, type='section')
                for s in sections_data
            ]
        
        # For full_section type with section_ids, resolve groups from those sections
        if t.type == 'full_section' and tariff_section_ids:
            for sid in tariff_section_ids:
                section_groups = section_groups_map.get(sid, [])
                for g in section_groups:
                    if g.id not in [ig.id for ig in included_groups]:
                        included_groups.append(TariffAccessInfo(
                            id=g.id,
                            name=g.name,
                            type='group'
                        ))
        
        tariffs.append(ClubTariffRead(
            id=t.id,
            name=t.name,
            description=t.description,
            type=t.type,
            payment_type=t.payment_type,
            price=float(t.price),
            duration_days=t.validity_days,
            sessions_count=t.sessions_count,
            freeze_days_total=t.freeze_days_total or 0,
            features=t.features or [],
            included_sections=included_sections,
            included_groups=included_groups,
        ))

    # Count sections and students
    sections_count = len(sections)

    students_query = (
        select(func.count(func.distinct(StudentEnrollment.student_id)))
        .select_from(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(
            and_(
                Section.club_id == club_id,
                StudentEnrollment.status.in_(
                    [EnrollmentStatus.active, EnrollmentStatus.new]
                ),
            )
        )
    )
    students_result = await session.execute(students_query)
    students_count = students_result.scalar() or 0

    return ClubDetailRead(
        id=club.id,
        name=club.name,
        description=club.description,
        city=club.city,
        address=club.address,
        logo_url=club.logo_url,
        cover_url=club.cover_url,
        phone=club.phone,
        telegram_url=club.telegram_url,
        instagram_url=club.instagram_url,
        whatsapp_url=club.whatsapp_url,
        working_hours=club.working_hours,
        sections_count=sections_count,
        students_count=students_count,
        tags=club.tags or [],
        sections=sections,
        tariffs=tariffs,
        coaches=coaches,
    )


@db_operation
async def get_student_club_ids(session: AsyncSession, student_id: int) -> List[int]:
    """Get IDs of clubs where student has memberships"""
    query = (
        select(Section.club_id)
        .select_from(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status.in_(
                    [EnrollmentStatus.active, EnrollmentStatus.new]
                ),
            )
        )
        .distinct()
    )
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


@db_operation
async def get_nearest_club(
    session: AsyncSession,
    latitude: float,
    longitude: float,
    student_id: Optional[int] = None,
) -> NearestClubResponse:
    """Get the nearest club to given coordinates"""
    # For simplicity, we'll use a basic distance calculation
    # In production, you might want to use PostGIS or similar

    # Get student's enrolled club IDs if student_id provided
    enrolled_club_ids = []
    if student_id:
        enrollment_query = (
            select(Section.club_id)
            .select_from(StudentEnrollment)
            .join(Group, StudentEnrollment.group_id == Group.id)
            .join(Section, Group.section_id == Section.id)
            .where(
                and_(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.status.in_(
                        [EnrollmentStatus.active, EnrollmentStatus.new]
                    ),
                )
            )
        )
        enrollment_result = await session.execute(enrollment_query)
        enrolled_club_ids = list(set([row[0] for row in enrollment_result.fetchall()]))

    # Get all clubs (or only enrolled clubs)
    clubs_query = select(Club)
    if enrolled_club_ids:
        clubs_query = clubs_query.where(Club.id.in_(enrolled_club_ids))

    result = await session.execute(clubs_query)
    clubs = result.scalars().all()

    if not clubs:
        return NearestClubResponse(club=None, distance_meters=None)

    # For demo purposes, return the first club with hardcoded coordinates
    # In production, clubs would have lat/lon columns
    # Using Almaty center as default location
    club = clubs[0]

    # Default club location (Almaty center)
    club_lat = 43.2220
    club_lon = 76.8512

    # Calculate distance using Haversine formula
    import math

    R = 6371e3  # Earth radius in meters
    phi1 = math.radians(latitude)
    phi2 = math.radians(club_lat)
    delta_phi = math.radians(club_lat - latitude)
    delta_lambda = math.radians(club_lon - longitude)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c

    return NearestClubResponse(
        club=ClubLocationRead(
            id=club.id,
            name=club.name,
            latitude=club_lat,
            longitude=club_lon,
            address=club.address,
        ),
        distance_meters=round(distance, 2),
    )
