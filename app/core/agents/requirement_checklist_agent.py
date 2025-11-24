from typing import Dict, Any, Optional, Tuple
import re
from tenacity import (
    AsyncRetrying,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    RetryError
)
from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class RequirementChecklistAgent:
    """Requirement Checklist Generation Agent - 专门生成需求清单"""
    
    SYSTEM_PROMPT = """# Requirement Checklist Generation Agent

You are a specialized agent responsible for generating requirement checklists for paper writing.

## Your Task

Generate a comprehensive requirement checklist file: `requirements_checklist.md`

## Output File

**File Name**: `requirements_checklist.md` (Chinese)

## Input Files

1. Read `[Paper_Title]_[Paper_Type]_paper_overview.txt` to get:
   - Paper Title
   - Paper Type (Method or Survey)
   - Research content details

2. Optionally read `paper_framework.tex` (if exists) to understand paper structure

## Content Structure

### Header
论文标题 (in English)

### Section 1: 画图需求 (Figure Requirements)

⚠️ **根据论文类型调整图表数量:**
- **Method类型**: 图表数量较少，通常2个图即可（如系统架构图、实验结果图）
- **Survey类型**: 图表数量可以较多，用于全面展示相关工作和方法对比

#### 1.1 算法图/Motivation图 (正文用)
- [ ] 系统架构图 - 展示方法框架（放在Method章节，Method类型必需）
- [ ] 动机图 - 展示问题背景和动机（放在Introduction章节，可选）
- [ ] 算法流程图 - 展示关键算法步骤（放在Method章节，Method类型推荐）
- [ ] 其他必要的算法示意图（根据实际需要）

#### 1.2 实验分析图 (实验部分用，Method类型为主)
- [ ] 主实验结果对比图 - 与baseline对比（放在Experiments章节，Method类型必需）
- [ ] 消融实验结果图 - 展示各模块贡献（放在Experiments章节，Method类型推荐）
- [ ] 定性结果展示 - 可视化案例（放在Experiments章节，可选）
- [ ] 参数分析图 - 超参数影响（放在Experiments章节，可选）

#### 1.3 Survey类型专用图表
- [ ] 方法分类对比图 - 展示不同方法类别（Survey类型推荐）
- [ ] 时间线图 - 展示领域发展历程（Survey类型推荐）
- [ ] 方法对比表格 - 全面对比各种方法（Survey类型必需）
- [ ] 应用场景图 - 展示不同应用领域（Survey类型可选）

#### 1.4 表格
- [ ] 主实验结果表 - 对比各方法性能（Method类型必需）
- [ ] 消融实验结果表 - 各模块性能变化（Method类型推荐）
- [ ] 数据集统计表 - 数据集基本信息（Method类型推荐）
- [ ] 方法对比表 - 全面对比各种方法（Survey类型必需）

### Section 2: 文字需求 (Text Requirements)

#### 2.1 第一部分: 摘要、引言
- [ ] 摘要 (Abstract): 背景、问题、方法、结果、意义
- [ ] 引言 (Introduction): 动机、现有方法、局限、贡献、论文组织

#### 2.2 第二部分: 方法
- [ ] 问题定义 - 数学符号定义输入、输出、目标
- [ ] 方法框架 - 整体流程描述（配合架构图）
- [ ] 核心模块 - 各模块详细说明和公式
- [ ] 算法伪代码 - 关键算法步骤
- ⚠️ 生成的方法要明确！！！

#### 2.3 第三部分: 实验分析
- [ ] 实验设置 - 数据集、baseline、评估指标、实现细节
- [ ] 主实验结果 - 与baseline对比和分析
- [ ] 消融实验 - 各模块贡献分析
- [ ] 结果讨论 - 实验发现和原因分析

## Requirements

1. **Be Specific**: Use actual dataset/model names from overview, not placeholders
2. **Be Concise**: Focus on essential requirements only
3. **Adjust by Paper Type**: 
   - Method类型: 图表数量较少（通常2个图即可）
   - Survey类型: 图表数量可以较多（用于全面展示和对比）
4. **Based on Real Content**: Reference actual research content from overview file

## Workflow

1. Extract information from paper overview content (provided by orchestrator):
   - Paper Title
   - Paper Type (Method or Survey)
   - Research content details

2. Optionally use LaTeX paper content (if provided by orchestrator) to understand structure

3. Generate checklist based on Paper Type:
   - Method: Focus on method figures and experimental results
   - Survey: Include more comparison figures and tables

4. Use specific names from overview (datasets, models, etc.)

## Output Format

⚠️ **CRITICAL**: You cannot save files directly. You must output in the following markdown format:

```path
requirements_checklist.md
```

```markdown
# [Paper Title in English]

─────────────────────────────────────────────────────────────────────────────
📊 第一大类: 画图需求
─────────────────────────────────────────────────────────────────────────────

⚠️ **根据论文类型调整图表数量:**
- **Method类型**: 图表数量较少，通常2个图即可（如系统架构图、实验结果图）
- **Survey类型**: 图表数量可以较多，用于全面展示相关工作和方法对比

**1.1 算法图/Motivation图 (正文用):**
- [ ] 系统架构图 - 展示方法框架（放在Method章节，Method类型必需）
- [ ] 动机图 - 展示问题背景和动机（放在Introduction章节，可选）
- [ ] 算法流程图 - 展示关键算法步骤（放在Method章节，Method类型推荐）
- [ ] 其他必要的算法示意图（根据实际需要）

**1.2 实验分析图 (实验部分用，Method类型为主):**
- [ ] 主实验结果对比图 - 与baseline对比（放在Experiments章节，Method类型必需）
- [ ] 消融实验结果图 - 展示各模块贡献（放在Experiments章节，Method类型推荐）
- [ ] 定性结果展示 - 可视化案例（放在Experiments章节，可选）
- [ ] 参数分析图 - 超参数影响（放在Experiments章节，可选）

**1.3 Survey类型专用图表:**
- [ ] 方法分类对比图 - 展示不同方法类别（Survey类型推荐）
- [ ] 时间线图 - 展示领域发展历程（Survey类型推荐）
- [ ] 方法对比表格 - 全面对比各种方法（Survey类型必需）
- [ ] 应用场景图 - 展示不同应用领域（Survey类型可选）

**1.4 表格:**
- [ ] 主实验结果表 - 对比各方法性能（Method类型必需）
- [ ] 消融实验结果表 - 各模块性能变化（Method类型推荐）
- [ ] 数据集统计表 - 数据集基本信息（Method类型推荐）
- [ ] 方法对比表 - 全面对比各种方法（Survey类型必需）

─────────────────────────────────────────────────────────────────────────────
✍️ 第二大类: 文字需求
─────────────────────────────────────────────────────────────────────────────

**2.1 第一部分: 摘要、引言**
- [ ] 摘要 (Abstract): 背景、问题、方法、结果、意义
- [ ] 引言 (Introduction): 动机、现有方法、局限、贡献、论文组织

**2.2 第二部分: 方法**
- [ ] 问题定义 - 数学符号定义输入、输出、目标
- [ ] 方法框架 - 整体流程描述（配合架构图）
- [ ] 核心模块 - 各模块详细说明和公式
- [ ] 算法伪代码 - 关键算法步骤
- ⚠️ 生成的方法要明确！！！

**2.3 第三部分: 实验分析**
- [ ] 实验设置 - 数据集、baseline、评估指标、实现细节
- [ ] 主实验结果 - 与baseline对比和分析
- [ ] 消融实验 - 各模块贡献分析
- [ ] 结果讨论 - 实验发现和原因分析
```

**Important**:
- Use ` ```path ` to specify the file name
- Use ` ```markdown ` to specify the markdown content
- The orchestrator will parse this markdown and save the file
- Do NOT include any file operations in your response"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service
    
    def _parse_markdown_output(self, response: str) -> Tuple[Optional[str], Optional[str]]:
        """
        解析 Agent 输出的 markdown 格式
        
        期望格式:
        ```path
        requirements_checklist.md
        ```
        
        ```markdown
        [content]
        ```
        
        Returns:
            (file_name, file_content) 或 (None, None) 如果解析失败
        """
        # 提取 path 块中的文件名（更宽松的匹配，支持多种格式）
        # 支持 ```path\n...\n``` 或 ```path ... ```（同一行）
        path_pattern = r'```path\s*\n?(.*?)\n?```'
        path_match = re.search(path_pattern, response, re.DOTALL)
        
        if not path_match:
            logger.warning("No ```path block found in agent output")
            return None, None
        
        file_name = path_match.group(1).strip()
        
        # 提取 markdown 块中的内容（更宽松的匹配）
        markdown_pattern = r'```markdown\s*\n?(.*?)\n?```'
        markdown_match = re.search(markdown_pattern, response, re.DOTALL)
        
        if not markdown_match:
            logger.warning("No ```markdown block found in agent output")
            return None, None
        
        file_content = markdown_match.group(1).strip()
        
        return file_name, file_content
    
    async def _generate_requirement_checklist_attempt(
        self,
        paper_overview: str,
        latex_content: Optional[str],
        user_original_input: Optional[str],
        temperature: float,
        max_tokens: int,
        model: Optional[str],
        attempt_number: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        单次生成尝试（内部方法，用于重试）
        
        Args:
            paper_overview: 从 Paper Overview Agent 得到的文本内容
            latex_content: 从 LaTeX Paper Generator Agent 得到的 LaTeX 内容
            user_original_input: 用户原始输入
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            attempt_number: 当前尝试次数
            
        Returns:
            成功时返回结果字典，失败时返回 None
        """
        # 重试时降低 temperature 以提高稳定性
        adjusted_temperature = max(0.3, temperature - (attempt_number - 1) * 0.1)
        
        # 构建用户消息
        user_content = f"""Please generate a requirement checklist based on the following information:

## Paper Overview (from Agent 1):
{paper_overview}

"""
        
        # 如果提供了 LaTeX 内容，则使用它
        if latex_content:
            user_content += f"""
## LaTeX Paper Content (from Agent 2):
{latex_content}

"""
        # 如果 Agent 2 跳过了，使用用户原始输入
        elif user_original_input:
            user_content += f"""
## User Original Input (Agent 2 was skipped):
{user_original_input}

"""
        
        user_content += """
Please generate a comprehensive requirement checklist based on the paper overview and structure information above."""
        
        # 重试时增强格式要求提示
        if attempt_number > 1:
            user_content += "\n\n⚠️ IMPORTANT: You MUST output in the exact format with ```path and ```markdown blocks. Ensure both blocks are present and properly formatted."
        
        # 构建消息
        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_content
            }
        ]
        
        # 调用 OpenAI
        raw_response, usage = await self.openai_service.chat_completion(
            messages=messages,
            temperature=adjusted_temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        # 解析输出
        file_name, file_content = self._parse_markdown_output(raw_response)
        
        if file_name is None or file_content is None:
            logger.warning(f"Attempt {attempt_number}: Failed to parse agent output")
            return None
        
        logger.info(f"Requirement checklist generated successfully on attempt {attempt_number}: {file_name}")
        
        return {
            "file_name": file_name,
            "file_content": file_content,
            "raw_response": raw_response,
            "usage": usage
        }
    
    async def generate_requirement_checklist(
        self,
        paper_overview: str,
        latex_content: Optional[str] = None,
        user_original_input: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成需求清单（带重试机制）
        
        Args:
            paper_overview: 从 Paper Overview Agent 得到的文本内容
            latex_content: 从 LaTeX Paper Generator Agent 得到的 LaTeX 内容（如果 Agent 2 没有跳过）
            user_original_input: 用户原始输入（如果 Agent 2 SKIPPED 则使用此输入）
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            {
                "file_name": str,
                "file_content": str,
                "raw_response": str,
                "usage": dict
            }
            
        Raises:
            ValueError: 如果所有重试都失败
        """
        def is_parse_failed(result: Optional[Dict[str, Any]]) -> bool:
            """检查解析是否失败"""
            return result is None
        
        attempt_number = 1
        last_result = None
        
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                retry=retry_if_result(is_parse_failed),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                before_sleep=before_sleep_log(logger, logger.warning)
            ):
                with attempt:
                    last_result = await self._generate_requirement_checklist_attempt(
                        paper_overview=paper_overview,
                        latex_content=latex_content,
                        user_original_input=user_original_input,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        model=model,
                        attempt_number=attempt_number
                    )
                    attempt_number += 1
                    if last_result is None:
                        # 触发重试
                        raise ValueError("Parse failed, will retry")
                    return last_result
        except RetryError:
            # 所有重试都失败
            logger.error(f"Failed to generate requirement checklist after {attempt_number - 1} attempts")
            raise ValueError("Agent output format is invalid after multiple retries. Expected markdown format with ```path and ```markdown blocks.")
        
        # 如果 somehow 到达这里，返回最后的结果
        if last_result is None:
            raise ValueError("Agent output format is invalid. Expected markdown format with ```path and ```markdown blocks.")
        return last_result
    
    async def generate_requirement_checklist_stream(
        self,
        paper_overview: str,
        latex_content: Optional[str] = None,
        user_original_input: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None
    ):
        """
        流式生成需求清单
        
        Args:
            paper_overview: 从 Paper Overview Agent 得到的文本内容
            latex_content: 从 LaTeX Paper Generator Agent 得到的 LaTeX 内容（如果 Agent 2 没有跳过）
            user_original_input: 用户原始输入（如果 Agent 2 SKIPPED 则使用此输入）
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            OpenAI 流式响应迭代器
        """
        # 构建用户消息
        user_content = f"""Please generate a requirement checklist based on the following information:

## Paper Overview (from Agent 1):
{paper_overview}

"""
        
        # 如果提供了 LaTeX 内容，则使用它
        if latex_content:
            user_content += f"""
## LaTeX Paper Content (from Agent 2):
{latex_content}

"""
        # 如果 Agent 2 跳过了，使用用户原始输入
        elif user_original_input:
            user_content += f"""
## User Original Input (Agent 2 was skipped):
{user_original_input}

"""
        
        user_content += """
Please generate a comprehensive requirement checklist based on the paper overview and structure information above."""
        
        # 构建消息
        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_content
            }
        ]
        
        # 调用 OpenAI 流式接口
        stream = await self.openai_service.chat_completion_stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        return stream

