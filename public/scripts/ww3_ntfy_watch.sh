#!/usr/bin/env bash
set -u

NTFY_SERVER="${NTFY_SERVER:-https://ntfy.sh}"
NTFY_TOPIC="${NTFY_TOPIC:-}"
NTFY_TITLE="${NTFY_TITLE:-WW3 jobs finished}"
NTFY_LABEL="${NTFY_LABEL:-WW3}"
NTFY_INTERVAL="${NTFY_INTERVAL:-60}"
NTFY_JOBS="${NTFY_JOBS:-}"
NTFY_WORKDIRS="${NTFY_WORKDIRS:-}"
NTFY_TIMEOUT_HOURS="${NTFY_TIMEOUT_HOURS:-0}"
NTFY_RESOLVE_IP="${NTFY_RESOLVE_IP:-}"

usage() {
    cat <<'EOF'
Usage: ww3_ntfy_watch.sh --topic TOPIC [options]

Options:
  --server URL          ntfy server URL, default: https://ntfy.sh
  --topic TOPIC         ntfy topic name
  --title TEXT          ntfy notification title
  --label TEXT          label shown in the message
  --jobs "ID ..."       Slurm job IDs to watch; default captures current user jobs
  --workdirs "DIR ..."  Work directories to inspect for success.log/fail.log
  --interval SEC        Poll interval, default: 60
  --timeout-hours N     Stop after N hours; 0 means no timeout
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --server) NTFY_SERVER="${2:-}"; shift 2 ;;
        --topic) NTFY_TOPIC="${2:-}"; shift 2 ;;
        --title) NTFY_TITLE="${2:-}"; shift 2 ;;
        --label) NTFY_LABEL="${2:-}"; shift 2 ;;
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

if [ -z "$NTFY_JOBS" ] && command -v squeue >/dev/null 2>&1; then
    NTFY_JOBS="$(squeue -h -u "${USER:-$(id -un)}" -o '%A' 2>/dev/null | awk '!seen[$1]++' | tr '\n' ' ')"
fi

started_at="$(date '+%F %T')"
start_epoch="$(date '+%s')"
host="$(hostname 2>/dev/null || echo unknown-host)"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

send_ntfy() {
    subject="$1"
    body="$2"
    if ! command -v curl >/dev/null 2>&1; then
        log "curl not found; notification not sent"
        return 1
    fi
    url="${NTFY_SERVER%/}/${NTFY_TOPIC}"
    if [ -n "$NTFY_RESOLVE_IP" ]; then
        curl -fsS --retry 10 --retry-delay 30 --connect-timeout 10 \
            --resolve "ntfy.sh:443:${NTFY_RESOLVE_IP}" \
            -H "Title: ${subject}" \
            -H "Tags: ocean,wave" \
            -d "$body" "$url" >/dev/null
    else
        curl -fsS --retry 10 --retry-delay 30 --connect-timeout 10 \
            -H "Title: ${subject}" \
            -H "Tags: ocean,wave" \
            -d "$body" "$url" >/dev/null
    fi
}

job_state() {
    job_id="$1"
    if command -v squeue >/dev/null 2>&1 && squeue -h -j "$job_id" 2>/dev/null | grep -q .; then
        echo "ACTIVE"
        return
    fi
    if command -v sacct >/dev/null 2>&1; then
        state="$(sacct -n -X -P -j "$job_id" --format=State,ExitCode 2>/dev/null | awk -F'|' 'NF {print $1 "|" $2; exit}')"
        if [ -n "$state" ]; then
            echo "$state"
            return
        fi
    fi
    echo "UNKNOWN_DONE"
}

workdir_state() {
    dir="$1"
    if [ -f "$dir/fail.log" ]; then
        echo "FAILED"
        return
    fi
    if [ -f "$dir/success.log" ]; then
        echo "COMPLETED"
        return
    fi
    child_count=0
    active_count=0
    failed_count=0
    completed_count=0
    while IFS= read -r child; do
        child_count=$((child_count + 1))
        if [ -f "$child/fail.log" ]; then
            failed_count=$((failed_count + 1))
        elif [ -f "$child/success.log" ]; then
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

log "ntfy watcher started on ${host}"
log "label=${NTFY_LABEL}"
log "topic=${NTFY_TOPIC}"
log "jobs=${NTFY_JOBS:-<none>}"
log "workdirs=${NTFY_WORKDIRS:-<none>}"

final_summary=""
final_ok=1

while :; do
    active=0
    final_summary="Started: ${started_at}
Host: ${host}
Label: ${NTFY_LABEL}
"

    if [ -n "$NTFY_JOBS" ]; then
        final_summary="${final_summary}
Jobs:
"
        for job in $NTFY_JOBS; do
            state="$(job_state "$job")"
            final_summary="${final_summary}- ${job}: ${state}
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
        final_summary="${final_summary}
Workdirs:
"
        for dir in $NTFY_WORKDIRS; do
            state="$(workdir_state "$dir")"
            final_summary="${final_summary}- ${dir}: ${state}
"
            case "$state" in
                ACTIVE*) active=$((active + 1)) ;;
                COMPLETED*) ;;
                *) final_ok=0 ;;
            esac
        done
    fi

    now_epoch="$(date '+%s')"
    elapsed=$((now_epoch - start_epoch))
    final_summary="${final_summary}
Elapsed: ${elapsed}s
"

    if [ "$active" -eq 0 ]; then
        break
    fi

    if [ "$NTFY_TIMEOUT_HOURS" != "0" ]; then
        timeout=$((NTFY_TIMEOUT_HOURS * 3600))
        if [ "$elapsed" -ge "$timeout" ]; then
            final_ok=0
            final_summary="${final_summary}
Timeout reached while ${active} target(s) were still active.
"
            break
        fi
    fi

    log "active targets: ${active}; polling again in ${NTFY_INTERVAL}s"
    sleep "$NTFY_INTERVAL"
done

if [ "$final_ok" -eq 1 ]; then
    title="${NTFY_TITLE}"
else
    title="${NTFY_TITLE} (failed)"
fi

log "sending ntfy notification"
if send_ntfy "$title" "$final_summary"; then
    log "notification sent"
    exit 0
fi
log "notification failed"
exit 1
