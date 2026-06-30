#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_OUTPUT:=/dev/null}"

record_review_status() {
	printf 'review_status=%s\n' "$1" >>"$GITHUB_OUTPUT"
}

record_review_model() {
	printf 'review_model=%s\n' "$1" >>"$GITHUB_OUTPUT"
}

normalize_opencode_output() {
	local output_file="$1"

	if python3 "$GITHUB_WORKSPACE/scripts/ci/opencode_review_normalize_output.py" \
		"$HEAD_SHA" "$RUN_ID" "$RUN_ATTEMPT" "$output_file"; then
		bash "$GITHUB_WORKSPACE/scripts/ci/opencode_review_approve_gate.sh" \
			"$HEAD_SHA" "$RUN_ID" "$RUN_ATTEMPT" "$output_file" >/dev/null
		return $?
	fi

	return 1
}

backoff_sleep() {
	local attempt="$1"
	local initial="${OPENCODE_BACKOFF_INITIAL_SECONDS:-20}"
	local max_sleep="${OPENCODE_BACKOFF_MAX_SECONDS:-300}"
	local sleep_for
	sleep_for=$((initial * (1 << (attempt - 1))))
	if [ "$sleep_for" -gt "$max_sleep" ]; then
		sleep_for="$max_sleep"
	fi
	printf '%s\n' "$sleep_for"
}

write_prompt() {
	local model_candidate="$1"
	local prompt_file="$2"
	local intro

	if [ -n "${OPENCODE_REVIEW_INTRO:-}" ]; then
		intro="$OPENCODE_REVIEW_INTRO"
	else
		intro="Review PR #\${PR_NUMBER} in \${OPENCODE_SOURCE_WORKDIR} with \${model_candidate}."
	fi
	cp "$GITHUB_WORKSPACE/scripts/ci/opencode_review_prompt_template.md" "$prompt_file"
	OPENCODE_REVIEW_INTRO="$intro" \
		PROMPT_MODEL_CANDIDATE="$model_candidate" \
		python3 "$GITHUB_WORKSPACE/scripts/ci/render_opencode_prompt_template.py" "$prompt_file"
}

run_one_model_attempt() {
	local model_candidate="$1"
	local attempt="$2"
	local attempts="$3"
	local agent="$4"
	local prompt_file="$5"
	local candidate_output_file="$6"
	local opencode_json_file="$7"
	local opencode_export_file="$8"
	local run_timeout_seconds opencode_status session_id

	run_timeout_seconds="${OPENCODE_RUN_TIMEOUT_SECONDS:-180}"

	rm -f "$opencode_json_file" "$opencode_export_file" "$candidate_output_file"
	set +e
	timeout --kill-after=30s "${run_timeout_seconds}s" opencode run "$(cat "$prompt_file")" \
		--pure \
		--agent "$agent" \
		--model "$model_candidate" \
		--format json \
		--title "PR #${PR_NUMBER} OpenCode bounded review ${model_candidate} attempt ${attempt}/${attempts}" >"$opencode_json_file"
	opencode_status=$?
	set -e
	if [ "$opencode_status" -ne 0 ]; then
		printf 'OpenCode %s attempt %s/%s failed with exit %s.\n' "$model_candidate" "$attempt" "$attempts" "$opencode_status"
		return 1
	fi

	session_id="$(jq -r 'select(.type == "step_start") | .sessionID' "$opencode_json_file" | tail -n 1)"
	if [ -z "$session_id" ] || [ "$session_id" = "null" ]; then
		printf 'OpenCode %s attempt %s/%s JSON output did not include a session id.\n' "$model_candidate" "$attempt" "$attempts"
		cat "$opencode_json_file"
		return 1
	fi
	if ! opencode export "$session_id" --pure >"$opencode_export_file"; then
		printf 'OpenCode %s attempt %s/%s session export did not complete.\n' "$model_candidate" "$attempt" "$attempts"
		return 1
	fi
	jq -r '.messages[] | select(.info.role == "assistant") | .parts[]? | select(.type == "text") | .text' "$opencode_export_file" >"$candidate_output_file"
	if [ ! -s "$candidate_output_file" ]; then
		printf 'OpenCode %s attempt %s/%s session export did not include assistant text.\n' "$model_candidate" "$attempt" "$attempts"
		cat "$opencode_export_file"
		return 1
	fi
	if ! normalize_opencode_output "$candidate_output_file"; then
		printf 'OpenCode %s attempt %s/%s output did not include a valid control conclusion.\n' "$model_candidate" "$attempt" "$attempts"
		cat "$candidate_output_file"
		return 1
	fi
	return 0
}

main() {
	local attempts deadline now remaining model_candidate attempt safe_model prompt_file candidate_output_file
	local opencode_json_file opencode_export_file agent retry_sleep original_run_timeout

	attempts="${OPENCODE_MODEL_ATTEMPTS:-3}"
	original_run_timeout="${OPENCODE_RUN_TIMEOUT_SECONDS:-180}"
	deadline=$((SECONDS + ${OPENCODE_TOTAL_RETRY_BUDGET_SECONDS:-2400}))
	: >"$OPENCODE_OUTPUT_FILE"
	cd "$OPENCODE_REVIEW_WORKDIR"

	for model_candidate in $OPENCODE_MODEL_CANDIDATES; do
		safe_model="${model_candidate//\//-}"
		prompt_file="${RUNNER_TEMP}/opencode-review-${safe_model}-prompt.md"
		candidate_output_file="${RUNNER_TEMP}/opencode-review-${safe_model}.md"
		opencode_json_file="${candidate_output_file}.jsonl"
		opencode_export_file="${candidate_output_file}.session.json"
		write_prompt "$model_candidate" "$prompt_file"
		for attempt in $(seq 1 "$attempts"); do
			now="$SECONDS"
			if [ "$now" -ge "$deadline" ]; then
				printf 'OpenCode model pool retry budget exhausted before %s attempt %s/%s.\n' "$model_candidate" "$attempt" "$attempts"
				record_review_status "exhausted"
				record_review_model ""
				exit 0
			fi
			remaining=$((deadline - now))
			OPENCODE_RUN_TIMEOUT_SECONDS="$original_run_timeout"
			if [ "$OPENCODE_RUN_TIMEOUT_SECONDS" -gt "$remaining" ]; then
				OPENCODE_RUN_TIMEOUT_SECONDS="$remaining"
			fi
			export OPENCODE_RUN_TIMEOUT_SECONDS
			agent="${OPENCODE_AGENT:-ci-review-fallback}"
			if [ "$attempt" -eq 1 ] && [ -n "${OPENCODE_FIRST_ATTEMPT_AGENT:-}" ]; then
				agent="$OPENCODE_FIRST_ATTEMPT_AGENT"
			fi
			if run_one_model_attempt "$model_candidate" "$attempt" "$attempts" "$agent" "$prompt_file" "$candidate_output_file" "$opencode_json_file" "$opencode_export_file"; then
				cp "$candidate_output_file" "$OPENCODE_OUTPUT_FILE"
				record_review_model "$model_candidate"
				record_review_status "success"
				exit 0
			fi
			retry_sleep="$(backoff_sleep "$attempt")"
			if [ $((SECONDS + retry_sleep)) -gt "$deadline" ]; then
				retry_sleep=$((deadline - SECONDS))
			fi
			if [ "$retry_sleep" -gt 0 ]; then
				printf 'Retrying OpenCode after exponential backoff of %ss.\n' "$retry_sleep"
				sleep "$retry_sleep"
			fi
		done
	done

	record_review_status "exhausted"
	record_review_model ""
}

main "$@"
