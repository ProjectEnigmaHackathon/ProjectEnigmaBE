"""
Workflow System Initialization

Initialize the LLM orchestrator and workflow registry on application startup.
"""

from app.core.logging_utils import log_workflow_function, LogLevel
from .workflow_registry import get_workflow_registry
from .orchestrator import get_orchestrator


@log_workflow_function(level=LogLevel.INFO, include_state=False, include_result=False, include_execution_time=True, log_errors=True)
def initialize_workflow_system():
    """
    Initialize the complete workflow system including:
    - Workflow registry with QA and Release workflows
    - LLM orchestrator for workflow classification
    
    This should be called during application startup.
    """
    try:
        print("🚀 Initializing Project Enigma Workflow System...")
        
        # Initialize workflow registry (this will create QA and Release workflow managers)
        print("📋 Setting up workflow registry...")
        registry = get_workflow_registry()
        registry.initialize()
        
        # Initialize orchestrator (this will create the LLM-powered classifier)
        print("🧠 Setting up LLM orchestrator...")
        orchestrator = get_orchestrator()
        
        # Verify initialization
        workflow_types = registry.list_workflow_types()
        print(f"✅ Workflow system initialized successfully!")
        print(f"   Available workflow types: {', '.join(workflow_types)}")
        print(f"   Orchestrator ready: {orchestrator is not None}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize workflow system: {e}")
        raise


@log_workflow_function(level=LogLevel.INFO, include_state=False, include_result=False, include_execution_time=True, log_errors=True)
async def test_orchestrator():
    """
    Test the orchestrator with sample messages to verify it's working correctly.
    """
    try:
        print("🧪 Testing orchestrator classification...")
        
        orchestrator = get_orchestrator()
        
        # Test cases
        test_cases = [
            ("Show me branches in frontend-app", "qa"),
            ("Create a release for version v2.1.0", "release"),
            ("Get Jira tickets for sprint-2024-01", "qa"),
            ("Automate deployment process", "release"),
            ("List all Confluence spaces", "qa"),
        ]
        
        for message, expected_type in test_cases:
            result = await orchestrator.classify_workflow(message)
            actual_type = result["workflow_type"]
            confidence = result.get("confidence", 0)
            
            status = "✅" if actual_type == expected_type else "⚠️"
            print(f"   {status} '{message}' → {actual_type} (confidence: {confidence:.2f})")
            
        print("🧪 Orchestrator testing completed!")
        
    except Exception as e:
        print(f"❌ Orchestrator test failed: {e}")
        raise