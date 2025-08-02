"""
QA Workflow for GitHub, Jira, and Confluence Queries

A comprehensive LangGraph agent that can answer queries about GitHub repositories,
Jira tickets, and Confluence pages using the respective API tools.
"""

import asyncio
from typing import Any, Dict, List, TypedDict, Annotated

from langchain_core.language_models import BaseLLM
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from .tools.github_tools import GitHubTools
from .tools.jira_tools import JiraTools
from .tools.confluence_tools import ConfluenceTools


class QAState(TypedDict):
    """State for the QA workflow."""
    messages: Annotated[List[BaseMessage], add_messages]


class QAWorkflow:
    """Comprehensive QA workflow for GitHub, Jira, and Confluence queries."""

    def __init__(self, llm: BaseLLM, use_mock: bool = True):
        """
        Initialize the QA workflow.

        Args:
            llm: Language model to use for reasoning
            use_mock: Whether to use mock APIs
        """
        self.github_tools = GitHubTools(use_mock=use_mock)
        self.jira_tools = JiraTools(use_mock=use_mock)
        self.confluence_tools = ConfluenceTools(use_mock=use_mock)
        
        # Combine all tools
        self.tools = []
        self.tools.extend(self.github_tools.get_tools())
        self.tools.extend(self.jira_tools.get_tools())
        self.tools.extend(self.confluence_tools.get_tools())
        
        self.graph = self._create_graph()
        self.llm = llm.bind_tools(self.tools)

    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow."""
        
        # Create the state graph
        workflow = StateGraph(QAState)
        
        # Create tool node
        tool_node = ToolNode(tools=self.tools)
        
        # Add nodes
        workflow.add_node("chatbot", self._llm_node)
        workflow.add_node("tools", tool_node)
        
        # Entry
        workflow.add_edge(START, "chatbot")
        
        # Conditional routing: tool call vs end
        workflow.add_conditional_edges(
            "chatbot",
            tools_condition
        )  # by default maps action→tools, __end__→END
        
        # Return loop from tools to chatbot
        workflow.add_edge("tools", "chatbot")
        
        return workflow.compile()

    def _llm_node(self, state: QAState) -> BaseMessage:
        """LLM node that decides what to do next."""
        messages = state["messages"]
        
        # Create comprehensive system prompt
        system_prompt = """
You are a comprehensive assistant that helps users query and manage GitHub repositories, Jira tickets, and Confluence pages using available tools.

Always follow this behavior:
1. If a user query can be answered using a tool, respond with a tool call — do NOT guess or answer from prior knowledge.
2. Only respond with tool calls when needed; otherwise, provide a direct and helpful answer.
3. Use tools exactly as documented. Ensure inputs are complete and correctly formatted.
4. If you're unsure about names/keys, assume they exist in the mock data.

You have access to the following tools:

## GitHub Tools:
- get_repository: Get information about a GitHub repository
- get_branches: Get all branches for a repository
- find_feature_branches: Find feature branches for JIRA ticket IDs
- check_merge_status: Check if one branch can be merged into another
- get_tags: Get all tags for a repository
- validate_github_connection: Validate GitHub API connection

## Jira Tools:
- get_tickets_by_fix_version: Get all Jira tickets for a specific fix version
- get_ticket: Get a specific Jira ticket by key
- search_tickets: Search Jira tickets using JQL (Jira Query Language)
- get_projects: Get all accessible Jira projects
- validate_jira_connection: Validate Jira API connection

## Confluence Tools:
- get_spaces: Get all accessible Confluence spaces
- get_page: Get a specific Confluence page by ID
- create_page: Create a new Confluence page
- update_page: Update an existing Confluence page
- search_pages: Search for pages in a Confluence space
- delete_page: Delete a Confluence page
- create_deployment_page: Create a standardized deployment documentation page
- validate_confluence_connection: Validate Confluence API connection

Assume the user wants accurate and up-to-date answers based on the respective platform data.

✅ Examples:
- GitHub: "Show branches in frontend-app" → Use `get_branches`
- GitHub: "Check if dev can be merged into main in core-platform" → Use `check_merge_status`
- GitHub: "List tags for api-service" → Use `get_tags`
- Jira: "Get all tickets for version v1.0.0" → Use `get_tickets_by_fix_version`
- Jira: "Search for tickets with status 'In Progress'" → Use `search_tickets`
- Jira: "Get ticket PROJ-123" → Use `get_ticket`
- Confluence: "Get all spaces" → Use `get_spaces`
- Confluence: "Get page with ID 12345" → Use `get_page`
- Confluence: "Create deployment page for v1.0.0" → Use `create_deployment_page`

🎯 Available mock data:
- GitHub repositories: api-service, frontend-app, core-platform, data-processor
- Jira projects: TEST, DEMO, PROJ
- Jira tickets: TEST-123, DEMO-456, PROJ-789
- Confluence spaces: TEST, DEMO, DOCS
- Confluence pages: Various mock pages with IDs

Never fabricate answers. If a tool is available, **use it**. Output **only tool calls** when one is needed.
"""

        # Add system message if not present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages

        # Get response from LLM
        response = self.llm.invoke(messages)
        print("\n\n\n response", response)
        # Return just the response message (add_messages will handle adding it to state)
        return {"messages": response}

    async def run(self, query: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Run the QA workflow with a query.

        Args:
            query: User query about GitHub, Jira, or Confluence
            config: Optional configuration for the workflow

        Returns:
            Dict containing the workflow result
        """
        # Initialize state
        initial_state = QAState(
            messages=[HumanMessage(content=query)]
        )

        # Run the workflow with default config if none provided
        if config is None:
            config = {}
        
        result = await self.graph.ainvoke(initial_state, config)
        
        # Extract the final answer from the last message
        final_message = result["messages"][-1]
        final_answer = final_message.content if hasattr(final_message, 'content') else str(final_message)
        
        return {
            "query": query,
            "answer": final_answer,
            "messages": result["messages"],
            "tool_results": result.get("tool_results", [])
        }


def create_qa_workflow(llm: BaseLLM, use_mock: bool = True) -> QAWorkflow:
    """
    Create a QA workflow instance.

    Args:
        llm: Language model to use
        use_mock: Whether to use mock APIs

    Returns:
        QAWorkflow instance
    """
    return QAWorkflow(llm, use_mock) 