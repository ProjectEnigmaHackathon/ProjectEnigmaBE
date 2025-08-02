"""
LLM-Powered Workflow Orchestrator

This orchestrator uses an LLM to decide which workflow to execute based on user input:
- QA Workflow: For GitHub, Jira, Confluence queries
- Release Workflow: For release automation tasks
"""

import asyncio
from typing import Dict, Any, Optional
from langchain_core.language_models import BaseLLM
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.logging_utils import log_workflow_function, LogLevel


class WorkflowClassification(BaseModel):
    """Pydantic model for workflow classification result."""
    workflow_type: str = Field(description="Type of workflow: 'qa' or 'release'")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(description="Brief explanation of the classification decision")


class WorkflowOrchestrator:
    """LLM-powered workflow orchestrator that decides between QA and Release workflows."""

    def __init__(self, llm: BaseLLM):
        """
        Initialize the orchestrator.
        
        Args:
            llm: Language model for workflow classification
        """
        self.llm = llm
        self.structured_llm = llm.with_structured_output(WorkflowClassification)
        
        # Classification prompt
        self.classification_prompt = ChatPromptTemplate.from_messages([
            ("system", self._get_classification_prompt()),
            ("human", "{user_message}")
        ])

    def _get_classification_prompt(self) -> str:
        """Get the system prompt for workflow classification."""
        return """
You are a workflow orchestrator. Based on the user's message, decide which workflow to execute.

Available workflows:
1. "qa" - For queries about GitHub repositories, Jira tickets, Confluence pages, searching, getting information
2. "release" - For release automation, branch management, deployment tasks, creating releases

Classification Guidelines:

QA Workflow Examples:
- "Show me branches in frontend-app"
- "Get Jira tickets for version v1.0.0" 
- "Search for tickets with status 'In Progress'"
- "Get ticket PROJ-123"
- "List all spaces in Confluence"
- "Get page with ID 12345"
- "What repositories do we have?"
- "Check merge status of feature branch"
- "Find feature branches for JIRA-123"

Release Workflow Examples:
- "Create a release for version v2.1.0"
- "Automate release process"
- "Start release workflow"
- "Deploy version v1.5.0 to production"
- "Create release branches"
- "Generate deployment documentation"
- "Merge sprint branches to develop"

Default to "qa" if uncertain, as it handles general queries.

Provide your classification with a workflow_type ("qa" or "release"), confidence score (0.0-1.0), and brief reasoning.
"""

    @log_workflow_function(level=LogLevel.INFO, include_state=False, include_result=True, include_execution_time=True, log_errors=True)
    async def classify_workflow(self, user_message: str) -> Dict[str, Any]:
        """
        Classify user message to determine appropriate workflow.
        
        Args:
            user_message: User's input message
            
        Returns:
            Dict containing workflow_type, confidence, and reasoning
        """
        try:
            # Format the prompt
            formatted_prompt = self.classification_prompt.format_messages(
                user_message=user_message
            )
            print("\nformatted_prompt - ",formatted_prompt)
            # Get structured response from LLM
            result: WorkflowClassification = await self.structured_llm.ainvoke(formatted_prompt)
            
            # Validate workflow type
            workflow_type = result.workflow_type
            if workflow_type not in ["qa", "release"]:
                workflow_type = "qa"  # Default fallback
            
            return {
                "workflow_type": workflow_type,
                "confidence": result.confidence,
                "reasoning": result.reasoning
            }
                
        except Exception as e:
            print(f"Error in workflow classification: {e}")
            # Fallback to simple keyword matching
            return self._fallback_classification(user_message)

    def _fallback_classification(self, user_message: str) -> Dict[str, Any]:
        """
        Fallback classification using simple keyword matching.
        
        Args:
            user_message: User's input message
            
        Returns:
            Dict containing workflow_type, confidence, and reasoning
        """
        message_lower = user_message.lower()
        
        # Release workflow keywords
        release_keywords = [
            "release", "deploy", "deployment", "automate", "create release",
            "merge sprint", "release branch", "rollback", "tag", "version",
            "sprint merge", "release process", "automation"
        ]
        
        # QA workflow keywords  
        qa_keywords = [
            "show", "get", "list", "search", "find", "branches", "tickets",
            "jira", "confluence", "github", "repository", "status", "page",
            "spaces", "merge status", "feature branch"
        ]
        
        release_score = sum(1 for keyword in release_keywords if keyword in message_lower)
        qa_score = sum(1 for keyword in qa_keywords if keyword in message_lower)
        
        if release_score > qa_score:
            return {
                "workflow_type": "release",
                "confidence": 0.7,
                "reasoning": f"Matched {release_score} release keywords"
            }
        else:
            return {
                "workflow_type": "qa", 
                "confidence": 0.7,
                "reasoning": f"Matched {qa_score} QA keywords or default to QA"
            }


# Global orchestrator instance
_orchestrator = None


def get_orchestrator() -> WorkflowOrchestrator:
    """Get the global workflow orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        from app.core.llm import get_llm
        _orchestrator = WorkflowOrchestrator(get_llm())
    return _orchestrator