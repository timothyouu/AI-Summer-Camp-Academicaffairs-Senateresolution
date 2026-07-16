# Demo Workflow

> **Note:** this frame map predates the 2026-07-14 sidebar unification (single 96px icon rail,
> role persisted via RoleProvider) — root `CLAUDE.md` supersedes it where they conflict. The
> page-to-page transitions and demo-path scripts below remain the navigation-transition
> reference.

This document maps how the website frames connect. Each transition uses the exact frame names.

## Entry and Workspace Selection

`login -> chats`  
Select **Employee / Faculty** and continue.

`login -> review overview`  
Select **Policy Reviewer / Writer** and continue.

## Employee / Faculty Workflow

### Ask a Policy Question

`chats -> chats answer`  
Enter a policy question, select a suggested question, or submit the prompt.

`chats answer -> chats answer`  
Ask a follow-up question and continue within the same conversation.

`chats answer -> chats`  
Select **New** to begin another conversation.

### Browse Past Conversations

`chats -> past chats (library)`  
Select **Library** in the sidebar.

`past chats (library) -> chats answer`  
Open a recent question to return to its complete answer and citations.

`past chats (library) -> topics`  
Open a saved policy to view its related topic and policy details.

### Browse Policy by Topic

`chats -> topic_list`  
Select **Topics** in the sidebar.

`topic_list -> topics`  
Select a policy category, such as **Tenure & Promotion**.

`topics -> chats answer`  
Select a common question or policy question to receive a cited answer.

`topics -> topic_list`  
Use the **Topics** breadcrumb to return to all policy categories.

## Policy Reviewer / Writer Workflow

### Reviewer Home

`review overview -> drafts`  
Select **Check a new resolution**, open **Drafts**, or start a new draft.

`review overview -> review`  
Submit pasted text or an attached document with **Start review**, or open a recent review.

`review overview -> conflict`  
Select **Open conflict log**, **Conflicts**, or **View all** beside open conflicts.

`review overview -> conflict review`  
Select a specific open conflict from the dashboard.

`review overview -> sources`  
Select **Upload a source** or **Sources** in the sidebar.

### Draft and Analysis

`drafts -> review`  
Select **Check for overlap and conflicts** to analyze the current draft.

`drafts -> review overview`  
Use the **Drafts** breadcrumb or reviewer navigation to leave the editor.

`review -> drafts`  
Return to the draft to revise language based on the analysis.

`review -> conflict review`  
Open a conflict finding to compare the affected policy sources.

`review -> review overview`  
Return to the review workspace after examining the results.

### Conflict Resolution

`conflict -> conflict review`  
Select a conflict row, such as **Service credit toward tenure**.

`conflict -> review overview`  
Use **Reviews** or the main reviewer navigation to return to the workspace.

`conflict review -> conflict`  
Add a resolution note and select **Mark resolved**. Return to the conflict log with the item marked resolved.

`conflict review -> review overview`  
Cancel or use reviewer navigation to return without resolving the conflict.

### Knowledge Sources

`sources -> review overview`  
After uploading or reviewing source status, return to the reviewer workspace.

## Switching Workspaces

`chats -> review overview`  
Use the role or workspace control to switch from **Employee / Faculty** to **Policy Reviewer / Writer**.

`review overview -> chats`  
Use the role or workspace control to switch from **Policy Reviewer / Writer** to **Employee / Faculty**.

## Global Navigation

These sidebar transitions are available wherever the destination appears for the active role:

- `New -> chats`
- `Ask -> chats`
- `Library -> past chats (library)`
- `Topics -> topic_list`
- `Drafts -> drafts`
- `Reviews -> review overview`
- `Conflicts -> conflict`
- `Sources -> sources`

## Complete Demo Paths

### Employee Question Demo

`login -> chats -> chats answer -> chats answer`

Choose Employee / Faculty, ask a question, review the cited response, and ask a follow-up.

### Employee Topic Discovery Demo

`login -> chats -> topic_list -> topics -> chats answer`

Choose Employee / Faculty, browse a topic, open Tenure & Promotion, and select a common question.

### Employee History Demo

`login -> chats -> past chats (library) -> chats answer`

Choose Employee / Faculty, open the library, and resume a previous conversation.

### Draft Review Demo

`login -> review overview -> drafts -> review`

Choose Policy Reviewer / Writer, prepare a draft, and check it for overlap and conflicts.

### Conflict Resolution Demo

`login -> review overview -> conflict -> conflict review -> conflict`

Choose Policy Reviewer / Writer, open the conflict log, review a conflict with its AI summary, add a resolution note, and mark it resolved.

### Source Management Demo

`login -> review overview -> sources -> review overview`

Choose Policy Reviewer / Writer, upload or inspect a trusted knowledge source, and return to the review workspace.
