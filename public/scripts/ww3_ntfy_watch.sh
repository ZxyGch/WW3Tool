#!/usr/bin/env bash
set -u

NTFY_SERVER="${NTFY_SERVER:-https://ntfy.sh}"
NTFY_TOPIC="${NTFY_TOPIC:-}"
NTFY_LABEL="${NTFY_LABEL:-WW3}"
NTFY_INTERVAL="${NTFY_INTERVAL:-60}"
NTFY_JOBS="${NTFY_JOBS:-}"
NTFY_WORKDIRS="${NTFY_WORKDIRS:-}"
NTFY_TIMEOUT_HOURS="${NTFY_TIMEOUT_HOURS:-0}"
NTFY_RESOLVE_IP="${NTFY_RESOLVE_IP:-}"
NTFY_MODE="${NTFY_MODE:-once}"

usage() {
    cat <<'EOF'
Usage: ww3_ntfy_watch.sh --topic TOPIC [options]

Options:
  --server URL          ntfy server URL, default: https://ntfy.sh
  --topic TOPIC         ntfy topic name
  --label TEXT          label shown in the message
  --mode once|all       once: exit after watched targets finish; all: keep watching forever
  --jobs "ID ..."       Slurm job IDs to watch; once mode captures current user jobs when empty
  --workdirs "DIR ..."  Work directories to inspect for success/fail markers
  --interval SEC        Poll interval, default: 60
  --timeout-hours N     once mode timeout; 0 means no timeout
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --server) NTFY_SERVER="${2:-}"; shift 2 ;;
        --topic) NTFY_TOPIC="${2:-}"; shift 2 ;;
        --label) NTFY_LABEL="${2:-}"; shift 2 ;;
        --mode) NTFY_MODE="${2:-once}"; shift 2 ;;
        --jobs) NTFY_JOBS="${2:-}"; shift 2 ;;
        --workdirs) NTFY_WORKDIRS="${2:-}"; shift 2 ;;
        --interval) NTFY_INTERVAL="${2:-60}"; shift 2 ;;
        --timeout-hours) NTFY_TIMEOUT_HOURS="${2:-0}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ -z "$NTFY_TOPIC" ]; then
    echo "Missing --topic or NTFY_TOPIC" >&2
    exit 2
fi

case "$NTFY_INTERVAL" in
    ''|*[!0-9]*|0) NTFY_INTERVAL=60 ;;
esac
case "$NTFY_MODE" in
    once|all) ;;
    *) echo "Invalid --mode: $NTFY_MODE" >&2; exit 2 ;;
esac

started_at="$(date '+%F %T')"
start_epoch="$(date '+%s')"
host="$(hostname 2>/dev/null || echo unknown-host)"
state_dir=".ntfy_watch_state_${NTFY_MODE}"
mkdir -p "$state_dir"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

format_elapsed() {
    local total="$1"
    local days=$((total / 86400))
    local rem=$((total % 86400))
    local hours=$((rem / 3600))
    rem=$((rem % 3600))
    local minutes=$((rem / 60))
    local seconds=$((rem % 60))
    local parts=""

    if [ "$days" -gt 0 ]; then
        parts="${days}d"
        if [ "$hours" -gt 0 ]; then
            parts="${parts} ${hours}h"
        fi
    elif [ "$hours" -gt 0 ]; then
        parts="${hours}h"
        if [ "$minutes" -gt 0 ]; then
            parts="${parts} ${minutes}m"
        fi
    elif [ "$minutes" -gt 0 ]; then
        parts="${minutes}m"
        if [ "$seconds" -gt 0 ]; then
            parts="${parts} ${seconds}s"
        fi
    else
        parts="${seconds}s"
    fi
    echo "$parts"
}

clean_state() {
    local state="$1"
    printf '%s' "${state%%|*}"
}

status_title() {
    local state="$1"
    local base
    base="$(printf '%s' "$(clean_state "$state")" | tr '[:lower:]' '[:upper:]')"
    case "$base" in
        COMPLETED*|OUT_OF_MEMORY*) echo "✅ Success"; return ;;
        CANCELLED*|PREEMPTED*) echo "⚠️ Cancel"; return ;;
        FAILED*|TIMEOUT*|NODE_FAIL*|BOOT_FAIL*|DEADLINE*) echo "❌ Fail"; return ;;
    esac
    case "$state" in
        COMPLETED*) echo "✅ Success" ;;
        FAILED*) echo "❌ Fail" ;;
        CANCELLED*|PREEMPTED*) echo "⚠️ Cancel" ;;
        *) echo "❌ Fail" ;;
    esac
}

overall_status_title() {
    local has_fail=0
    local has_cancel=0
    for raw in "$@"; do
        case "$(status_title "$raw")" in
            *Fail*) has_fail=1 ;;
            *Cancel*) has_cancel=1 ;;
        esac
    done
    if [ "$has_fail" -eq 1 ]; then
        echo "❌ Fail"
        return
    fi
    if [ "$has_cancel" -eq 1 ]; then
        echo "⚠️ Cancel"
        return
    fi
    echo "✅ Success"
}

send_ntfy() {
    subject="$1"
    body="$2"
    if ! command -v curl >/dev/null 2>&1; then
        log "curl not found; notification not sent"
        return 1
    fi
    url="${NTFY_SERVER%/}/${NTFY_TOPIC}"
    local curl_err_file="${state_dir}/curl_last_error.log"
    local rc=0
    if [ -n "$NTFY_RESOLVE_IP" ]; then
        curl -fsS --retry 3 --retry-delay 5 --connect-timeout 10 --max-time 30 \
            --resolve "ntfy.sh:443:${NTFY_RESOLVE_IP}" \
            -H "Title: ${subject}" \
            -H "Tags: ocean" \
            -d "$body" "$url" >/dev/null 2>"$curl_err_file"
        rc=$?
    else
        curl -fsS --retry 3 --retry-delay 5 --connect-timeout 10 --max-time 30 \
            -H "Title: ${subject}" \
            -H "Tags: ocean" \
            -d "$body" "$url" >/dev/null 2>"$curl_err_file"
        rc=$?
    fi
    if [ "$rc" -ne 0 ]; then
        log "send_ntfy FAILED (curl exit=$rc) topic=${NTFY_TOPIC} subject=${subject}"
        if [ -s "$curl_err_file" ]; then
            log "curl error: $(cat "$curl_err_file")"
        fi
        return 1
    fi
    return 0
}

current_user_jobs() {
    if command -v squeue >/dev/null 2>&1; then
        squeue -h -u "${USER:-$(id -un)}" -o '%A' 2>/dev/null | awk '!seen[$1]++'
    fi
}

job_active() {
    job_id="$1"
    command -v squeue >/dev/null 2>&1 && squeue -h -j "$job_id" 2>/dev/null | grep -q .
}

job_name() {
    job_id="$1"
    if command -v sacct >/dev/null 2>&1; then
        name="$(sacct -n -X -P -j "$job_id" --format=JobName 2>/dev/null | head -1)"
        if [ -n "$name" ] && [ "$name" != "None" ]; then
            echo "$name"
            return
        fi
    fi
    echo "$job_id"
}

job_state() {
    job_id="$1"
    if job_active "$job_id"; then
        echo "ACTIVE"
        return
    fi
    if command -v sacct >/dev/null 2>&1; then
        state="$(sacct -n -X -P -j "$job_id" --format=State,ExitCode --starttime="${started_at%% *}" 2>/dev/null | awk -F'|' 'NF {print $1 "|" $2; exit}')"
        if [ -n "$state" ]; then
            echo "$state"
            return
        fi
    fi
    echo "UNKNOWN_DONE"
}

workdir_state() {
    dir="$1"
    if [ -f "$dir/fail" ]; then
        echo "FAILED"
        return
    fi
    if [ -f "$dir/success" ]; then
        echo "COMPLETED"
        return
    fi
    child_count=0
    active_count=0
    failed_count=0
    completed_count=0
    while IFS= read -r child; do
        [ -n "$child" ] || continue
        child_count=$((child_count + 1))
        if [ -f "$child/fail" ]; then
            failed_count=$((failed_count + 1))
        elif [ -f "$child/success" ]; then
            completed_count=$((completed_count + 1))
        else
            active_count=$((active_count + 1))
        fi
    done <<EOF
$(find "$dir" -mindepth 1 -maxdepth 2 -type f -name params.yml -print 2>/dev/null | xargs -n 1 dirname 2>/dev/null | sort -u)
EOF
    if [ "$child_count" -eq 0 ]; then
        echo "ACTIVE"
    elif [ "$active_count" -gt 0 ]; then
        echo "ACTIVE children=${active_count}/${child_count}"
    elif [ "$failed_count" -gt 0 ]; then
        echo "FAILED children_failed=${failed_count} completed=${completed_count}"
    else
        echo "COMPLETED children=${completed_count}"
    fi
}

remember_active_job() {
    job_id="$1"
    [ -n "$job_id" ] || return
    touch "$state_dir/job_${job_id}.active"
}

notify_finished_job() {
    job_id="$1"
    state="$(job_state "$job_id")"
    case "$state" in
        ACTIVE*) return 1 ;;
    esac

    # Guard against sacct lag: if job just left squeue but sacct hasn't
    # caught up yet (UNKNOWN_DONE), wait one more poll cycle before notifying.
    if [ "$state" = "UNKNOWN_DONE" ]; then
        pending_file="$state_dir/job_${job_id}.pending_done"
        if [ ! -f "$pending_file" ]; then
            touch "$pending_file"
            log "job ${job_id} left squeue but sacct has no record yet; deferring one cycle"
            return 1
        fi
        rm -f "$pending_file"
    fi

    rm -f "$state_dir/job_${job_id}.active" "$state_dir/job_${job_id}.pending_done"
    if [ -f "$state_dir/job_${job_id}.done" ]; then
        return 0
    fi
    local jname elapsed_secs elapsed_text finished_at
    jname="$(job_name "$job_id")"
    finished_at="$(date '+%F %T')"
    elapsed_secs=$(($(date '+%s') - start_epoch))
    elapsed_text="$(format_elapsed "$elapsed_secs")"
    {
        echo "Started: ${started_at}"
        echo "Finished: ${finished_at}"
        echo "JobID: ${job_id}"
        echo "JobName: ${jname}"
        echo "State: $(clean_state "$state")"
        echo "Elapsed: ${elapsed_text}"
    } > "$state_dir/message_${job_id}.txt"
    send_ntfy "$(status_title "$state")" "$(cat "$state_dir/message_${job_id}.txt")" \
        && touch "$state_dir/job_${job_id}.done"
    return 0
}

notify_workdir_if_finished() {
    dir="$1"
    key="$(printf '%s' "$dir" | cksum | awk '{print $1}')"
    state="$(workdir_state "$dir")"
    case "$state" in
        ACTIVE*) return 1 ;;
    esac
    previous="$(cat "$state_dir/workdir_${key}.state" 2>/dev/null || true)"
    if [ "$previous" = "$state" ]; then
        return 0
    fi
    printf '%s\n' "$state" > "$state_dir/workdir_${key}.state"
    workdir_name="$(basename "$dir")"
    local elapsed_secs elapsed_text finished_at
    finished_at="$(date '+%F %T')"
    elapsed_secs=$(($(date '+%s') - start_epoch))
    elapsed_text="$(format_elapsed "$elapsed_secs")"
    body="Started: ${started_at}
Finished: ${finished_at}
Workdir: ${dir}
State: $(clean_state "$state")
Elapsed: ${elapsed_text}"
    send_ntfy "$(status_title "$state")" "$body"
    return 0
}

run_once_mode() {
    if [ -z "$NTFY_JOBS" ]; then
        NTFY_JOBS="$(current_user_jobs | tr '\n' ' ')"
    fi
    log "jobs=${NTFY_JOBS:-<none>}"
    log "workdirs=${NTFY_WORKDIRS:-<none>}"

    while :; do
        active=0
        final_ok=1
        summary="Started: ${started_at}
"
        if [ -n "$NTFY_JOBS" ]; then
            summary="${summary}
Jobs:
"
            for job in $NTFY_JOBS; do
                state="$(job_state "$job")"
                summary="${summary}- JobID ${job}: $(clean_state "$state")
"
                case "$state" in
                    ACTIVE*) active=$((active + 1)) ;;
                    COMPLETED*) ;;
                    UNKNOWN_DONE*) ;;
                    *) final_ok=0 ;;
                esac
            done
        fi

        if [ -n "$NTFY_WORKDIRS" ]; then
            summary="${summary}
Workdirs:
"
            for dir in $NTFY_WORKDIRS; do
                state="$(workdir_state "$dir")"
                summary="${summary}- ${dir}: $(clean_state "$state")
"
                case "$state" in
                    ACTIVE*) active=$((active + 1)) ;;
                    COMPLETED*) ;;
                    *) final_ok=0 ;;
                esac
            done
        fi

        elapsed=$(($(date '+%s') - start_epoch))
        [ "$active" -eq 0 ] && break

        if [ "$NTFY_TIMEOUT_HOURS" != "0" ]; then
            timeout=$((NTFY_TIMEOUT_HOURS * 3600))
            if [ "$elapsed" -ge "$timeout" ]; then
                final_ok=0
                summary="${summary}
Timeout reached while ${active} target(s) were still active.
"
                break
            fi
        fi

        log "active targets: ${active}; polling again in ${NTFY_INTERVAL}s"
        sleep "$NTFY_INTERVAL"
    done

    title_states=""
    if [ -n "$NTFY_JOBS" ]; then
        for job in $NTFY_JOBS; do
            title_states="${title_states}$(job_state "$job") "
        done
    fi
    if [ -n "$NTFY_WORKDIRS" ]; then
        for dir in $NTFY_WORKDIRS; do
            title_states="${title_states}$(workdir_state "$dir") "
        done
    fi
    if [ -n "$title_states" ]; then
        # shellcheck disable=SC2086
        title="$(overall_status_title $title_states)"
    elif [ "$final_ok" -eq 1 ]; then
        title="✅ Success"
    else
        title="❌ Fail"
    fi
    finished_at="$(date '+%F %T')"
    elapsed=$(($(date '+%s') - start_epoch))
    summary="${summary}
Finished: ${finished_at}
Elapsed: $(format_elapsed "$elapsed")
"
    send_ntfy "$title" "$summary"
}

run_all_mode() {
    log "persistent watcher enabled"
    log "workdirs=${NTFY_WORKDIRS:-<none>}"
    while :; do
        for job in $(current_user_jobs); do
            remember_active_job "$job"
        done
        for active_file in "$state_dir"/job_*.active; do
            [ -e "$active_file" ] || continue
            job="${active_file##*/job_}"
            job="${job%.active}"
            notify_finished_job "$job" || true
        done
        for dir in $NTFY_WORKDIRS; do
            notify_workdir_if_finished "$dir" || true
        done
        sleep "$NTFY_INTERVAL"
    done
}

log "ntfy watcher started on ${host}"
log "mode=${NTFY_MODE}"
log "label=${NTFY_LABEL}"
log "topic=${NTFY_TOPIC}"

# Startup connectivity test: send a test notification so the user knows
# the watcher is alive and curl can reach ntfy.sh from this host.
log "sending startup test notification..."
if send_ntfy "watcher started" "Mode: ${NTFY_MODE}
Topic: ${NTFY_TOPIC}
Jobs: ${NTFY_JOBS:-auto-detect}
Started: ${started_at}"; then
    log "startup notification sent OK"
else
    log "WARNING: startup notification FAILED — check network/DNS from this host to ${NTFY_SERVER}"
fi

if [ "$NTFY_MODE" = "all" ]; then
    run_all_mode
else
    run_once_mode
fi
