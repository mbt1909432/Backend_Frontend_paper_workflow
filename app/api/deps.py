from fastapi import Depends
from app.services.openai_service import OpenAIService
from app.services.anthropic_service import AnthropicService
from app.core.agent import Agent
from app.core.agents.paper_overview_agent import PaperOverviewAgent
from app.core.agents.latex_paper_generator_agent import LaTeXPaperGeneratorAgent
from app.core.agents.requirement_checklist_agent import RequirementChecklistAgent
from app.core.agents.vision_agent import VisionAgent
from app.core.workflows.paper_generation_workflow import PaperGenerationWorkflow


# 依赖注入：OpenAI 服务实例
def get_openai_service() -> OpenAIService:
    """获取 OpenAI 服务实例"""
    return OpenAIService()


# 依赖注入：Agent 实例
def get_agent(openai_service: OpenAIService = Depends(get_openai_service)) -> Agent:
    """获取 Agent 实例"""
    return Agent(openai_service)


# 依赖注入：Paper Overview Agent 实例
def get_paper_overview_agent(openai_service: OpenAIService = Depends(get_openai_service)) -> PaperOverviewAgent:
    """获取 Paper Overview Agent 实例"""
    return PaperOverviewAgent(openai_service)


# 依赖注入：LaTeX Paper Generator Agent 实例
def get_latex_paper_generator_agent(openai_service: OpenAIService = Depends(get_openai_service)) -> LaTeXPaperGeneratorAgent:
    """获取 LaTeX Paper Generator Agent 实例"""
    return LaTeXPaperGeneratorAgent(openai_service)


# 依赖注入：Requirement Checklist Agent 实例
def get_requirement_checklist_agent(openai_service: OpenAIService = Depends(get_openai_service)) -> RequirementChecklistAgent:
    """获取 Requirement Checklist Agent 实例"""
    return RequirementChecklistAgent(openai_service)


# 依赖注入：Anthropic 服务实例
def get_anthropic_service() -> AnthropicService:
    """获取 Anthropic 服务实例"""
    return AnthropicService()


# 依赖注入：Vision Agent 实例
def get_vision_agent(anthropic_service: AnthropicService = Depends(get_anthropic_service)) -> VisionAgent:
    """获取 Vision Agent 实例"""
    return VisionAgent(anthropic_service)


# 依赖注入：Paper Generation Workflow 实例
def get_paper_generation_workflow(
    paper_overview_agent: PaperOverviewAgent = Depends(get_paper_overview_agent),
    latex_paper_agent: LaTeXPaperGeneratorAgent = Depends(get_latex_paper_generator_agent),
    requirement_checklist_agent: RequirementChecklistAgent = Depends(get_requirement_checklist_agent)
) -> PaperGenerationWorkflow:
    """获取 Paper Generation Workflow 实例"""
    return PaperGenerationWorkflow(
        paper_overview_agent=paper_overview_agent,
        latex_paper_agent=latex_paper_agent,
        requirement_checklist_agent=requirement_checklist_agent
    )

