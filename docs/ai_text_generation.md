# AI Generation / Text Generation

OpenAI Text and Google Text reuse the provider keys already configured in addon
preferences (including the existing environment-key preference). Neither UI nor
logs expose keys. Generation runs in a daemon worker; Blender data is updated
only by the main-thread timer. Scene load, Undo/Redo and addon shutdown discard
pending local results. Submitted remote requests may still finish.

Choose Generate Text or Translate, a model, and optional instructions. Translate
accepts any target language name. The Prompt field handles short requests; for
long text, choose a Blender Text datablock, Edit Input, or Paste Input. A selected
multiline document takes precedence over the short prompt. Clear its selector to
return to the short prompt. Results are stored as Blender Text documents and
survive saving the .blend. Open Result shows the complete text; Copy Result
copies it to the system clipboard. API failures preserve the previous result.

## Model catalog checked 2026-10-24

Sources:
- https://developers.openai.com/api/docs/models
- https://developers.openai.com/api/docs/models/all
- https://ai.google.dev/gemini-api/docs/models

OpenAI defaults to GPT-6 Luna for inexpensive text and translation, with
GPT-6.1 Sol and GPT-6 Astra for progressively stronger tasks. The catalog also
includes previous-generation GPT-5.4 Mini, GPT-5.4, GPT-5.4 Pro, GPT-5.2 and
GPT-5.2 Pro. Deprecated nano/GPT-5 models are not suggested by the preset list.

Google defaults to Gemini 3.5 Flash-Lite. Additional choices are 3.1 Flash-Lite,
3.8 Flash, 3.6 Flash, Gemini 4 Argon, 3.1 Pro Preview and 3 Flash Preview. The
2.5 Flash-Lite / Flash / Pro options are marked as requiring legacy access.
Image, audio, video, embedding and transcription models are excluded.

Custom Model ID permits an exact new or account-specific model ID. Model access
depends on the provider account, project, quota and preview availability. The
bundled list is documentation-verified, not an assertion of access by every key.

OpenAI uses POST /v1/responses, aggregates all output_text message parts, excludes
reasoning parts and sets store=false. Google uses models.generateContent with
systemInstruction and excludes thought parts. Max Output Tokens limits output
including model reasoning where applicable. Partial output is identified in
status; increase the limit if no visible answer fits the reasoning budget.

API references:
- https://developers.openai.com/api/docs/guides/text
- https://ai.google.dev/api/generate-content

## Validation

Blender 5.2 tests use mocked HTTP responses and do not make paid API requests:
- test_ai_text_blender.py: payloads, Unicode, multiple response parts, quota
  errors with redacted keys, blocked responses, concurrent providers, translation
  instructions, custom models, old-result preservation, schema capture,
  .blend persistence and repeated addon registration.
- test_ai_text_ui_blender.py: native provider controls, clipboard copy/paste.
- test_refactor_settings_lifecycle_blender.py: existing settings lifecycle.

## Asset Name translation (2026-10-25)

The globe button beside FAB, Unity and Unreal Asset Name fields translates the
current name into English, normalizes words to underscores and writes it back:
`Пустынные камни` -> `Desert_Rocks`. It is also available in the Phase 2 Batch
Finalization Start dialog and the FAB rename dialogs. It translates the name
only; it does not run renaming or processing.

Preferences -> API -> Default Text / Translation Model controls these short
requests. The default is GPT-6 Luna. The shared menu includes GPT-6.1 Sol,
GPT-5.4 Mini and text Flash/Flash-Lite Gemini choices from the existing catalog,
including Gemini 3.5 Flash-Lite, 3.6 Flash and 3.8 Flash. Provider keys and their
environment preference are reused automatically. This does not override model
choices in the full OpenAI Text / Google Text editor.

Both providers are requested to return a JSON object with exactly one
`asset_name` string. The response is validated before assignment. Invalid,
partial or failed replies preserve the original field. Requests run off the
main thread. A field edited while waiting is preserved; closing the Batch
Finalization dialog, scene load, Undo/Redo and addon shutdown discard pending
local results. The status below the field shows progress or the API error.

Validation: test_asset_translation_blender.py checks both structured payloads,
all target fields, provider/model selection, stale edits and errors.
test_asset_translation_popup_blender.py opens the real native Phase 2 dialog.
test_asset_translation_live_blender.py is an explicit paid live smoke using
existing addon keys; both GPT-6 Luna and Gemini 3.5 Flash-Lite returned
`Desert_Rocks` during validation on 2026-10-25.
