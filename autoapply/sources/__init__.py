from .jobstreet import JobStreet
from .linkedin import LinkedIn
from .mycareersfuture import MyCareersFuture

ALL_SOURCES = {s.name: s for s in (MyCareersFuture, JobStreet, LinkedIn)}
