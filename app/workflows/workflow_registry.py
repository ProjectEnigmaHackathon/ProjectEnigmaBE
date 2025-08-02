"""
Workflow Registry

Manages different workflow managers and provides a unified interface
for accessing QA and Release workflows.
"""

from typing import Dict, Optional
from langgraph.graph.state import CompiledStateGraph

from app.core.logging_utils import log_workflow_function, LogLevel
from .workflow_manager import WorkflowManager
from .qa_workflow import create_qa_workflow
from .release_workflow import create_release_workflow


class WorkflowRegistry:
    """Registry for different workflow managers."""
    
    def __init__(self):
        """Initialize the workflow registry."""
        self._managers: Dict[str, WorkflowManager] = {}
        self._initialized = False
        
    @log_workflow_function(level=LogLevel.INFO, include_state=False, include_result=False, include_execution_time=True, log_errors=True)
    def initialize(self):
        """Initialize all workflow managers."""
        if self._initialized:
            return
            
        try:
            from app.core.llm import get_llm
            llm = get_llm()
            
            # Initialize QA Workflow Manager
            print("Initializing QA workflow...")
            qa_workflow = create_qa_workflow(llm=llm, use_mock=True)
            qa_manager = WorkflowManager(qa_workflow.graph, enable_persistence=True)
            self._managers["qa"] = qa_manager
            
            # Initialize Release Workflow Manager
            print("Initializing Release workflow...")
            release_workflow = create_release_workflow()
            release_manager = WorkflowManager(release_workflow, enable_persistence=True)
            self._managers["release"] = release_manager
            
            self._initialized = True
            print("Workflow registry initialized successfully")
            
        except Exception as e:
            print(f"Error initializing workflow registry: {e}")
            raise
    
    def get_manager(self, workflow_type: str) -> Optional[WorkflowManager]:
        """
        Get workflow manager by type.
        
        Args:
            workflow_type: Type of workflow ("qa" or "release")
            
        Returns:
            WorkflowManager instance or None if not found
        """
        if not self._initialized:
            self.initialize()
            
        return self._managers.get(workflow_type)
    
    def list_workflow_types(self) -> list:
        """Get list of available workflow types."""
        if not self._initialized:
            self.initialize()
            
        return list(self._managers.keys())
    
    def get_all_workflows(self) -> Dict[str, list]:
        """Get all workflows from all managers."""
        if not self._initialized:
            self.initialize()
            
        all_workflows = {}
        for workflow_type, manager in self._managers.items():
            workflows = manager.list_workflows()
            all_workflows[workflow_type] = workflows
            
        return all_workflows


# Global registry instance
_registry = None


def get_workflow_registry() -> WorkflowRegistry:
    """Get the global workflow registry instance."""
    global _registry
    if _registry is None:
        _registry = WorkflowRegistry()
    return _registry


def get_workflow_manager_by_type(workflow_type: str) -> Optional[WorkflowManager]:
    """
    Get workflow manager by type.
    
    Args:
        workflow_type: Type of workflow ("qa" or "release")
        
    Returns:
        WorkflowManager instance or None if not found
    """
    registry = get_workflow_registry()
    return registry.get_manager(workflow_type)


def get_workflow_manager_by_id(workflow_id: str) -> Optional[WorkflowManager]:
    """
    Get workflow manager by workflow ID.
    
    This searches all managers to find which one contains the workflow.
    
    Args:
        workflow_id: ID of the workflow
        
    Returns:
        WorkflowManager instance that contains the workflow, or None
    """
    registry = get_workflow_registry()
    
    for manager in registry._managers.values():
        if manager.get_workflow_status(workflow_id):
            return manager
            
    return None