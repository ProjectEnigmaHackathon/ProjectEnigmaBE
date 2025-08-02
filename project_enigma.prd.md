# Project Enigma - Product Requirements Document

## Product Overview

Project Enigma is an AI-powered internal tool that automates release documentation creation by integrating JIRA tickets, GitHub branches, and Confluence documentation. The solution reduces manual effort from 1 day per developer to minutes by automating the entire release workflow process.

## Target Users

- Team leads responsible for release management
- Senior developers who create release deployment documentation
- DevOps engineers managing multi-repository releases

## Functional Requirements

| Requirement ID | Description                           | User Story                                                                                                                                                           | Expected Behavior/Outcome                                                                                                                                   |
| -------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR001          | Chat-First Main Interface             | As a user, I want to see a chat interface as the main landing page so I can immediately start interacting with the AI system.                                        | The main dashboard displays a prominent chat interface with input area and message history, eliminating need for navigation to access core functionality.   |
| FR002          | Repository Selection Dropdown         | As a user, I want to select target repositories from a dropdown for each chat session so I can specify which repos are part of my release.                           | A dropdown component displays all configured repositories with multi-select capability, allowing users to choose relevant repos for each release workflow.  |
| FR003          | Settings Panel Access                 | As a user, I want to access settings through a left panel button so I can manage repository configurations.                                                          | A left sidebar contains a settings button that opens a dedicated settings page for repository management without disrupting the main chat interface.        |
| FR004          | Repository Configuration              | As a user, I want to add and manage repository names in settings so I can configure which repos the system can work with.                                            | The settings page provides an interface to add, edit, and delete repository names with validation and persistence across sessions.                          |
| FR005          | Structured Chat Input                 | As a user, I want to provide release information in a structured format (repos, release type, sprint name, fix version) so the AI can process my request accurately. | The chat interface accepts structured input with clear labels for repos, release type (release/hotfix), sprint name, and JIRA fix version.                  |
| FR006          | Chat History Persistence              | As a user, I want my previous conversations to be remembered so I can refer back to previous releases and continue workflows.                                        | The system stores and displays chat history across sessions, allowing users to scroll through previous conversations and resume interrupted workflows.      |
| FR007          | Real-time Streaming Responses         | As a user, I want to see AI responses stream in real-time so I can monitor progress of long-running operations.                                                      | The chat interface displays streaming text responses with progress indicators, showing real-time updates as the system processes each workflow step.        |
| FR008          | JIRA Ticket Collection                | As a user, I want the system to automatically collect all JIRA tickets with specified fix versions so I can ensure all work items are included in the release.       | The system connects to JIRA API, retrieves tickets filtered by fix version, and displays ticket IDs and summaries in the chat response.                     |
| FR009          | Feature Branch Discovery              | As a user, I want the system to find all feature branches containing JIRA ticket IDs so I can verify all development work is tracked.                                | The system searches GitHub repositories for branches matching pattern "feature/{JIRA-ID}" and reports found/missing branches for each ticket.               |
| FR010          | Merge Status Validation               | As a user, I want to verify that all feature branches are merged into sprint branches so I can ensure code integration is complete.                                  | The system checks merge status of each feature branch into specified sprint branch and reports any unmerged branches with repository and branch details.    |
| FR011          | Human Approval Checkpoint             | As a user, I want to approve the merging of sprint branches to develop so I can maintain control over the release process.                                           | The system pauses workflow and prompts for user confirmation before proceeding with sprint-to-develop merges, allowing cancellation if needed.              |
| FR012          | Automated Sprint Branch Merging       | As a user, I want sprint branches to be automatically merged to develop after my approval so I can ensure consistent integration across repositories.                | Upon user approval, the system creates merge requests/pull requests from sprint branches to develop branches for all specified repositories.                |
| FR013          | Release Branch Creation               | As a user, I want release branches to be created from develop branches with semantic versioning so I can prepare code for production deployment.                     | The system creates release branches following semantic versioning (v1.0.0, v2.0.0) by analyzing existing tags and incrementing major version appropriately. |
| FR014          | Pull Request Generation               | As a user, I want PRs created from release branches to master so I can track and review the final deployment changes.                                                | The system automatically creates pull requests from release branches to master branches and captures PR URLs for inclusion in deployment documentation.     |
| FR015          | Release Tag Creation                  | As a user, I want release tags created with proper versioning so I can maintain version history and enable rollbacks.                                                | The system creates Git tags on release branches with semantic version numbers and includes metadata about the release.                                      |
| FR016          | Rollback Branch Preparation           | As a user, I want rollback branches created from master in standardized format so I can quickly revert if deployment issues occur.                                   | The system creates rollback branches from master using format "rollback/v-{Fix version}" and captures branch URLs for documentation.                        |
| FR017          | Confluence Documentation Generation   | As a user, I want a structured deployment document created in Confluence so I can share deployment plans with stakeholders.                                          | The system creates a Confluence page with deployment and rollback sections for each repository, including Jenkins URLs, PR links, and branch information.   |
| FR018          | Branch Not Found Error Handling       | As a user, I want to be notified when feature branches cannot be found for JIRA tickets so I can investigate missing development work.                               | The system reports in chat response which JIRA tickets do not have corresponding feature branches, allowing manual investigation.                           |
| FR019          | Merge Conflict Error Handling         | As a user, I want to be alerted about merge conflicts during automated operations so I can resolve them manually.                                                    | The system detects merge conflicts during automated merging and reports affected repositories and branches in the chat response.                            |
| FR020          | Semantic Version Management           | As a user, I want the system to automatically determine the next version number so I can ensure proper version progression.                                          | The system analyzes existing Git tags, follows semantic versioning rules, and increments major version (v1.0.0 → v2.0.0) for new releases.                  |
| FR021          | Repository Status Visibility          | As a user, I want to see which repositories are up to date in their release process so I can track overall progress.                                                 | The system provides status indicators showing which repos have completed each workflow step (branch merging, PR creation, etc.).                            |
| FR022          | Standardized Branch Naming Convention | As a user, I want the system to follow our established naming conventions so integration works seamlessly with existing workflows.                                   | The system enforces feature branch pattern "feature/{JIRA-ID}" and accepts user-defined sprint branch names through the UI.                                 |
| FR023          | Multiple Repository Support           | As a user, I want to process releases spanning 3-30 repositories simultaneously so I can handle varying release scopes efficiently.                                  | The system processes all selected repositories in parallel, provides per-repo status updates, and handles partial failures gracefully.                      |
| FR024          | Authentication Management             | As a user, I want secure authentication to JIRA, GitHub, and Confluence so I can access private repositories and create documentation.                               | The system uses AWS Secrets Manager to store API credentials and maintains secure connections to all integrated services.                                   |
| FR025          | Deployment Documentation Format       | As a user, I want deployment documents to follow our standard format so stakeholders can easily find required information.                                           | The Confluence page follows specified template with deployment plan (job URL, PR link, branch) and rollback plan (rollback branch) for each repository.     |

## Non-Functional Requirements

| Requirement ID | Description                | Expected Behavior/Outcome                                                                                                  |
| -------------- | -------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| NFR001         | AWS Cloud Hosting          | System deployed on AWS using S3+CloudFront for frontend, ECS/Lambda/EC2 for backend, ensuring scalability and reliability. |
| NFR002         | API Rate Limit Handling    | System gracefully handles API rate limits from JIRA, GitHub, and Confluence without breaking workflow execution.           |
| NFR003         | Real-time Progress Updates | System provides immediate feedback and progress indicators during long-running operations to maintain user engagement.     |
| NFR004         | Session Persistence        | System maintains user sessions and chat history across browser refreshes and multiple login sessions.                      |
| NFR005         | Error Recovery             | System provides clear error messages and allows workflow continuation or restart after resolving issues.                   |

## Technical Architecture

- **Frontend:** React (hosted on S3 + CloudFront)
- **Backend:** FastAPI + LangGraph (deployed on ECS/Lambda/EC2)
- **Database:** MySQL or in-memory storage
- **Authentication:** AWS Secrets Manager
- **Integrations:** JIRA API, GitHub API, Confluence API
- **Deployment:** AWS Cloud Infrastructure

## Success Metrics

- **Time Savings:** Reduce deployment documentation creation from 1 day per developer to under 1 hour
- **Error Reduction:** Eliminate manual errors in branch tracking and documentation formatting
- **Process Standardization:** Ensure consistent deployment documentation across all releases
- **User Adoption:** 100% adoption by team leads and senior developers within 3 months

## Constraints and Assumptions

- Users are technical personnel comfortable with release management concepts
- Standardized branch naming conventions are followed across all repositories
- JIRA, GitHub, and Confluence instances are properly configured and accessible
- Release frequency varies between weekly and monthly cycles
- System will be used internally only with no monetization requirements
