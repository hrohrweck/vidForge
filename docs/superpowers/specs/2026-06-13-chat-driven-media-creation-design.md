# Design: Card-Driven Interactive Media Creation in Chat

**Date:** 2026-06-13  
**Status:** Design review  
**Related systems:** Chat orchestrator, job/scene API, worker dispatcher, frontend chat UI.

## 1. Goal

Let users create videos (and eventually other media) entirely from the chat, with the assistant presenting actionable review cards at each pipeline stage. Users must be able to approve, edit, and regenerate content without leaving the conversation, while still receiving asynchronous updates if they switch away.

## 2. Non-goals

- This design does not replace the dedicated scene editor; it complements it.
- Phase 1 does not include per-scene editing or media-library replacement; those are phase 2.
- It does not change billing, storage, or provider selection beyond what the existing API already supports.

## 3. Guiding principles

1. **Cards are the primary interaction surface.** The assistant explains in text, but the user acts through message cards.
2. **Reuse existing infrastructure.** Use the existing job/scene REST API and the existing job WebSocket; avoid building a parallel pipeline.
3. **History is the state machine.** Every stage is persisted as a chat message, so users can leave and resume at any point.
4. **Autonomy is opt-in per conversation.** Default is confirmation; a user can switch to autonomous mode with a phrase like “just do it.”

## 4. Architecture

### 4.1 High-level flow (confirmation mode)

```text
User request
    ↓
Assistant calls present_job_draft → frontend renders JobDraftCard
    ↓
User edits/approves → card calls POST /jobs
    ↓
Worker runs planning
    ↓
JobChatNotifier posts ScenePlanCard
    ↓
User clicks Generate images → card calls POST /jobs/{id}/scenes/generate-all-images
    ↓
Worker runs generating_images
    ↓
JobChatNotifier posts ImageReviewCard
    ↓
User clicks Generate videos → card calls POST /jobs/{id}/scenes/generate-all-videos
    ↓
Worker runs generating_videos
    ↓
JobChatNotifier posts VideoReviewCard
    ↓
User clicks Export → card calls POST /jobs/{id}/export
    ↓
Worker runs rendering
    ↓
JobChatNotifier posts final completion message
```

### 4.2 Autonomous mode

- Assistant skips `present_job_draft` and the intermediate review cards.
- It creates the job and sets the conversation autonomy flag to `autonomous`.
- The worker runs all stages sequentially (or the scene-based equivalents are chained automatically).
- Only the final completion message is posted to chat.

## 5. Message card schema

A new attachment kind `job_card` is added to `Message.attachments`.

```json
{
  "kind": "job_card",
  "card_type": "job_draft | scene_plan | image_review | video_review | export_ready | job_completed | job_error",
  "job_id": "<uuid> | null",
  "title": "Scenes planned",
  "data": { "stage-specific payload" },
  "actions": ["create", "generate_images", "generate_videos", "export", "retry", "cancel"]
}
```

### 5.1 `job_draft` data

```json
{
  "prompt": "Niki dancing to hip hop music",
  "duration": 25,
  "style": "realistic",
  "aspect_ratio": "16:9",
  "avatars": [{"avatar_id": "...", "avatar_name": "Niki"}],
  "image_model": "...",
  "video_model": "...",
  "estimated_cost": 3.5
}
```

### 5.2 `scene_plan` data

```json
{
  "scenes": [
    {
      "scene_number": 1,
      "start_time": 0.0,
      "end_time": 5.0,
      "visual_description": "...",
      "image_prompt": "...",
      "mood": "energetic",
      "camera_movement": "dynamic tracking shot"
    }
  ]
}
```

### 5.3 `image_review` data

```json
{
  "scenes": [
    {
      "scene_number": 1,
      "thumbnail_url": "/api/jobs/{id}/scenes/{scene_id}/thumbnail",
      "status": "image_ready | failed | pending"
    }
  ]
}
```

### 5.4 `video_review` data

Similar to image review but with clip preview URLs.

### 5.5 `job_completed` data

```json
{
  "output_url": "/api/jobs/{id}/download",
  "preview_url": "/api/jobs/{id}/preview",
  "thumbnail_url": "/api/jobs/{id}/thumbnail"
}
```

## 6. Backend components

### 6.1 `JobChatNotifier`

New service in `app/services/job_chat_notifier.py`. Invoked from the worker dispatcher after each stage transition.

Responsibilities:
- Load the linked conversation from `Job.chat_conversation_id`.
- Check the conversation autonomy flag; skip intermediate cards if `autonomous`.
- Create an assistant `Message` with a short text summary and the correct `job_card` attachment.
- Broadcast `chat_message_appended` on `/ws/chat/{conversation_id}`.
- For the final stage, include the output video as an attachment (replaces/enhances `_post_completion_message`).

### 6.2 `ChatAutonomyService`

New service in `app/services/chat_autonomy_service.py`.

Responsibilities:
- Read the default from `UserSettings.preferences["chat_autonomy"]` (`confirm` | `autonomous`).
- Read/write a per-conversation override from `Conversation.metadata`.
- Provide:
  - `get_mode(conversation_id)`
  - `set_mode(conversation_id, mode)`
  - `should_confirm(conversation_id)`

Storage choice: `Conversation.metadata` JSONB is preferred because it keeps the override in the conversation row and survives reloads without extra Redis logic.

### 6.3 New chat tools

| Tool | Input | Output | Behavior |
|---|---|---|---|
| `present_job_draft` | `template`, `prompt`, `duration`, `avatars`, etc. | Draft payload with `kind: "job_draft"` | Returns the draft for the frontend card. Skipped in autonomous mode. |
| `set_chat_autonomy` | `mode: "confirm" \| "autonomous"` | `{mode}` | Sets the conversation override. |
| `get_chat_autonomy` | none | `{mode}` | Lets the assistant check current mode. |

### 6.4 API endpoints

- `POST /api/chat/conversations/{id}/autonomy` — set mode.
- `GET /api/chat/conversations/{id}/autonomy` — read mode.
- Existing endpoints used by cards:
  - `POST /jobs`
  - `GET /jobs/{id}`
  - `GET /jobs/{id}/scenes`
  - `POST /jobs/{id}/scenes/generate-all-images`
  - `POST /jobs/{id}/scenes/generate-all-videos`
  - `POST /jobs/{id}/export`
  - `POST /jobs/{id}/retry`
  - `POST /jobs/{id}/cancel`

## 7. Frontend components

### 7.1 `MessageBubble` extension

Render attachments with `kind === "job_card"` by delegating to a card component based on `card_type`.

### 7.2 Card components

- `JobDraftCard` — editable form with Create/Cancel.
- `ScenePlanCard` — read-only scene list with Generate images action.
- `ImageReviewCard` — thumbnail grid with Generate videos action.
- `VideoReviewCard` — clip preview grid with Export action.
- `JobCompletedCard` — final video with download.
- `JobErrorCard` — error details with Retry/Cancel.

Each card:
- Subscribes to `/ws/jobs/{job_id}` to update progress.
- Refreshes job state on mount via `GET /jobs/{id}`.
- Calls the appropriate API endpoint for its primary action.
- Shows inline validation or error states.

### 7.3 `ChatPanel` changes

- When a `chat_message_appended` event arrives for a job-card message, fetch the message and append it.
- No additional polling is required because WebSockets already push updates.

## 8. Resume and async behavior

- Every card is self-contained and rehydrates from `GET /jobs/{id}` and the job WebSocket.
- A user returning to a conversation sees the last card and can click its action if the job is in the corresponding stage.
- If a stage completed while the user was away, the backend already posted the next card message, which the frontend receives via the conversation WebSocket.
- Final output is delivered by the existing completion-message flow.

## 9. Error handling

- Validation errors from `POST /jobs` are shown inline in `JobDraftCard`.
- Stage failures post a `job_error` card with Retry and Cancel actions.
- Retry uses the existing `retry_job` tool/endpoint.
- Cancel uses the existing cancel endpoint and rolls the job back to the previous stable stage.

## 10. Testing strategy

- Unit tests for `JobChatNotifier` (mock DB + message creation).
- Unit tests for `ChatAutonomyService`.
- Tests for the new chat tools (`present_job_draft`, `set_chat_autonomy`).
- Frontend component tests for each card type.
- Integration test: create job → planning → verify card message posted → simulate Generate images click → verify worker queued.

## 11. Implementation phases

### Phase 1 — Approval + read-only review

1. Add `Conversation.metadata` autonomy storage.
2. Implement `ChatAutonomyService` and API endpoints.
3. Implement `set_chat_autonomy` and `present_job_draft` chat tools.
4. Implement `JobChatNotifier` for `planned`, `images_ready`, `videos_ready`, `completed`, `failed`.
5. Wire notifier into worker dispatcher.
6. Create frontend card components for draft, scene plan, image review, video review, completed, error.
7. Update `MessageBubble` to render `job_card` attachments.
8. Add user setting default for chat autonomy.
9. Update system prompt so the assistant knows when to confirm vs. run autonomously.
10. Tests and documentation.

### Phase 2 — Inline editing & per-scene control

1. Editable scene fields in `ScenePlanCard` with PATCH calls.
2. Per-scene regenerate/replace actions in image/video review cards.
3. Media-library picker for replacing images.
4. Chat-command editing tools as fallback.
5. Per-stage or per-scene model override.

## 12. Decisions

- The assistant posts a short textual summary alongside every card (e.g., “Planned 5 scenes. Review them below.”).
- Draft cards display the estimated cost when cost estimation is available.
- The system default for new users is `confirm`.
- `Conversation.metadata` is the source of truth for the per-conversation autonomy override.
