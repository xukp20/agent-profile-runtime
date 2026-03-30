from __future__ import annotations

from agent_profile_runtime.providers.models import ProviderInvocation, ProviderParsedOutput, RunError, UsageInfo
from agent_profile_runtime.providers import ProviderKind

from .models import RunEffectiveConfig, RunResult


def build_run_result(
    *,
    run_id: str,
    session_id: str,
    provider_kind: ProviderKind,
    provider_invocation: ProviderInvocation,
    effective_config: RunEffectiveConfig,
    parsed_output: ProviderParsedOutput,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    provider_exit_code: int | None,
    artifacts: dict[str, str | None],
) -> RunResult:
    status = "succeeded"
    error = parsed_output.error
    ok = True
    if error is not None:
        status = "failed"
        ok = False
    elif provider_exit_code not in (0, None):
        error = RunError(
            code="cli_error",
            message=f"provider exited with code {provider_exit_code}",
            retryable=False,
        )
        status = "failed"
        ok = False
    provider_session_id = parsed_output.provider_session_id or provider_invocation.provider_session_id or ""
    if not provider_session_id:
        error = RunError(
            code="missing_provider_session_id",
            message="unable to determine provider session id from run output",
            retryable=False,
        )
        status = "failed"
        ok = False
    return RunResult(
        ok=ok,
        status=status,  # type: ignore[arg-type]
        run_id=run_id,
        session_id=session_id,
        provider_kind=provider_kind,
        provider_session_id=provider_session_id,
        prompt_used=effective_config.prompt_used,
        prompt_source=effective_config.prompt_source,
        output_mode=effective_config.output_mode,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        final_text=parsed_output.final_text,
        usage=parsed_output.usage,
        error=error,
        provider_exit_code=provider_exit_code,
        artifacts=artifacts,
        effective=effective_config.to_dict(),
    )

