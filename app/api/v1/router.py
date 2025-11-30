from fastapi import APIRouter
from app.api.v1.endpoints import agent, health, paper_overview, latex_paper, requirement_checklist, workflow, workflow_tasks, vision, auth, admin, token_usage, arxiv_crawl


api_router = APIRouter()

# 注册路由
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(paper_overview.router, prefix="/paper-overview", tags=["paper-overview"])
api_router.include_router(latex_paper.router, prefix="/latex-paper", tags=["latex-paper"])
api_router.include_router(requirement_checklist.router, prefix="/requirement-checklist", tags=["requirement-checklist"])
api_router.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
api_router.include_router(workflow_tasks.router, prefix="/workflow/tasks", tags=["workflow-tasks"])
api_router.include_router(vision.router, prefix="/vision", tags=["vision"])
api_router.include_router(token_usage.router, prefix="/token-usage", tags=["token-usage"])
api_router.include_router(arxiv_crawl.router, prefix="/arxiv-crawl", tags=["arxiv-crawl"])

