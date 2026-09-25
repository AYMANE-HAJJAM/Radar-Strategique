from types import MappingProxyType

from app.core.agent_errors import AgentError
from app.core.radar_agent_base import BaseRadarAgent
from app.modules.radar1_markets.service import MarketsRadarAgent
from app.modules.radar2_projects.service import ProjectsRadarAgent
from app.modules.radar3_institutions.service import InstitutionsRadarAgent
from app.modules.radar4_policies.service import PoliciesRadarAgent
from app.modules.radar5_funding.service import FundingRadarAgent


class UnknownRadarError(AgentError):
    kind = 'unknown_radar'


class RadarAgentRegistry:
    def __init__(self, agent_types):
        self._agents = {}
        for agent_type in agent_types:
            if not issubclass(agent_type, BaseRadarAgent):
                raise TypeError('Radar agents must implement BaseRadarAgent.')
            if agent_type.code in self._agents:
                raise ValueError('Duplicate radar registration.')
            self._agents[agent_type.code] = agent_type

    def resolve(self, code):
        try:
            return self._agents[code]()
        except KeyError:
            raise UnknownRadarError('Radar inconnu.') from None

    def catalog(self):
        return MappingProxyType({code: self.resolve(code) for code in self._agents})


RADAR_AGENT_REGISTRY = RadarAgentRegistry((
    MarketsRadarAgent, ProjectsRadarAgent, InstitutionsRadarAgent,
    PoliciesRadarAgent, FundingRadarAgent,
))

# Compatibility catalog used by Telegram routing / menus.
RADARS = RADAR_AGENT_REGISTRY.catalog()
