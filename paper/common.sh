#!/bin/bash
# ======================================================================
# 論文実験スクリプト共通の設定・関数（各 paper/*.sh から source する）
#
# run_experiment_normal.py は結果を time_dependent_output/<query_set>/ 直下に
# 固定ファイル名で書き出す（= staging）。本スクリプト群は各実行の直後に
# 結果を time_dependent_output/rq*/... へ移動して整理する。staging にある既存の
# 同名ファイルは実行中だけ一時退避し、終了後に元の場所へ戻す（protect_file / restore_file）。
#
# 環境変数:
#   DRY_RUN=1   実行せずコマンドを表示するだけ（ファイル操作も一切しない）
#   FORCE=1     出力先に結果があっても再実行する（既定: 結果があればスキップ＝再開可能）
#   REUSE=0     同一条件の結果を別RQからコピーせず、改めて実行する（既定: 1=再利用）
#   PY          python 実行体（既定: .venv/bin/python）
#   CONTAINER   PostgreSQL コンテナ名（既定: mv_postgres）
#   TIMEOUT     プルーニングなし最適化の打ち切り時間（既定: 24h）
# ======================================================================

set -u -o pipefail

PAPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${PAPER_DIR}/.." && pwd)"
cd "${REPO_ROOT}" || exit 1

PY="${PY:-.venv/bin/python}"
CONTAINER="${CONTAINER:-mv_postgres}"
DRY_RUN="${DRY_RUN:-0}"
FORCE="${FORCE:-0}"
REUSE="${REUSE:-1}"
TIMEOUT="${TIMEOUT:-24h}"

TD="time_dependent_output"
MAIN="scripts/run_experiment_normal.py"
B_MAX=500   # 論文の既定ストレージ制約 (MB)

log() { echo "[$(date '+%F %T')] $*"; }
die() { log "ERROR: $*"; exit 1; }

# ファイルを変更する操作は必ず run 経由で行う（DRY_RUN=1 なら表示のみ）
run() {
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] $*"
        return 0
    fi
    "$@"
}

# run_main <logfile> <timeout|-> <args...>
#   run_experiment_normal.py を実行し、出力をログにも保存する。
#   戻り値は python（timeout 指定時は timeout）の終了コード（124 = タイムアウト）。
run_main() {
    local logfile=$1 to=$2
    shift 2
    if [ "${DRY_RUN}" = "1" ]; then
        if [ "${to}" = "-" ]; then
            echo "  [dry-run] ${PY} ${MAIN} $*"
        else
            echo "  [dry-run] timeout ${to} ${PY} ${MAIN} $*"
        fi
        return 0
    fi
    mkdir -p "$(dirname "${logfile}")"
    if [ "${to}" = "-" ]; then
        env PYTHONUNBUFFERED=1 "${PY}" "${MAIN}" "$@" 2>&1 | tee -a "${logfile}"
    else
        timeout "${to}" env PYTHONUNBUFFERED=1 "${PY}" "${MAIN}" "$@" 2>&1 | tee -a "${logfile}"
    fi
    return "${PIPESTATUS[0]}"
}

# ベンチマーク前に PostgreSQL を再起動してキャッシュをクリアする
restart_container() {
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] docker restart ${CONTAINER}"
        return 0
    fi
    log "PostgreSQL コンテナを再起動: ${CONTAINER}"
    docker restart "${CONTAINER}" > /dev/null || die "docker restart に失敗"
    sleep 15
    until docker exec "${CONTAINER}" pg_isready -U postgres > /dev/null 2>&1; do
        sleep 2
    done
}

# ----------------------------------------------------------------------
# staging（time_dependent_output/<set>/ 直下）にある既存ファイルの保護
#
# 1) 結果 JSON: 実行の直前に「これから書き込まれる名前」と衝突する既存ファイルだけを
#    <set>/_stash/in_use/ へ一時退避し、結果を rq*/ へ回収したら元の場所へ戻す。
#    異常終了・中断時も EXIT trap で戻す（元の場所が空いている場合のみ）。
#    → 既存の結果（例: job-ceb-2-q{N}/ にある Fig.9 の元データ）は元の場所に残る。
# 2) 中間生成物（timestep_*.sql, static_*initial_mvs.sql, jobs/）: Phase 7/8 が削除して
#    作り直すため、post-opt 系スクリプトの初回だけ <set>/_stash/intermediates_<日時>/ へ退避する
#    （以降は本スクリプト群が生成したものなので上書きしてよい。目印は .paper_staging）。
# ----------------------------------------------------------------------

# protect_file <query_set> <file_name>
protect_file() {
    local src="${TD}/$1/$2"
    local stash="${TD}/$1/_stash/in_use"
    [ -e "${src}" ] || return 0
    if [ -e "${stash}/$2" ]; then
        die "退避先に同名ファイルがあります（前回の中断の残り）: ${stash}/$2 — 手動で確認してください"
    fi
    log "一時退避: ${src} -> ${stash}/"
    run mkdir -p "${stash}"
    run mv "${src}" "${stash}/$2"
}

# restore_file <query_set> <file_name>
restore_file() {
    local dst="${TD}/$1/$2"
    local stashed="${TD}/$1/_stash/in_use/$2"
    [ -e "${stashed}" ] || return 0
    if [ -e "${dst}" ]; then
        log "WARNING: ${dst} が存在するため ${stashed} を戻せません（手動で確認してください）"
        return 0
    fi
    log "復元: ${stashed} -> ${dst}"
    run mv "${stashed}" "${dst}"
}

# EXIT 時に、一時退避したまま残っているファイルを元の場所へ戻す
restore_all() {
    local f set name
    shopt -s nullglob
    for f in "${TD}"/*/_stash/in_use/*; do
        set=$(basename "$(dirname "$(dirname "$(dirname "${f}")")")")
        name=$(basename "${f}")
        restore_file "${set}" "${name}"
    done
    shopt -u nullglob
}
[ "${DRY_RUN}" = "1" ] || trap restore_all EXIT

# backup_intermediates <query_set> : 中間生成物の初回退避（post-opt 系スクリプトの冒頭で呼ぶ）
backup_intermediates() {
    local dir="${TD}/$1"
    [ -f "${dir}/.paper_staging" ] && return 0
    local stash
    stash="${dir}/_stash/intermediates_$(date +%Y%m%d_%H%M%S)"
    local -a files=()
    shopt -s nullglob
    files+=("${dir}"/timestep_*.sql)
    files+=("${dir}"/static_*initial_mvs.sql)
    shopt -u nullglob
    [ -d "${dir}/jobs" ] && files+=("${dir}/jobs")
    if [ ${#files[@]} -gt 0 ]; then
        log "中間生成物を退避: ${dir} 直下の ${#files[@]} 件 -> ${stash}/"
        run mkdir -p "${stash}"
        run mv "${files[@]}" "${stash}/"
    fi
    run mkdir -p "${dir}"
    run touch "${dir}/.paper_staging"
}

# is_done <file>... : すべて存在すれば 0（FORCE=1 のときは常に 1）
is_done() {
    [ "${FORCE}" = "1" ] && return 1
    local f
    for f in "$@"; do
        [ -f "${f}" ] || return 1
    done
    return 0
}

# collect <query_set> <dest_dir> <staging側ファイル名> [出力先ファイル名]
collect() {
    local src="${TD}/$1/$3"
    local dst="$2/${4:-$3}"
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] mv ${src} ${dst}"
        return 0
    fi
    [ -f "${src}" ] || die "結果ファイルが見つかりません: ${src}"
    mkdir -p "$2"
    mv -f "${src}" "${dst}"
    log "  -> ${dst}"
}

# reuse_copy <src_dir> <dest_dir> <file>...
#   同一条件の実行結果を別 RQ からコピーする（論文データも同一ファイルを共有している）。
#   REUSE=0 または src に揃っていなければ 1 を返す（呼び出し側で実行にフォールバック）。
reuse_copy() {
    local src=$1 dest=$2
    shift 2
    [ "${REUSE}" = "1" ] || return 1
    local f
    for f in "$@"; do
        [ -f "${src}/${f}" ] || return 1
    done
    log "再利用: ${src} -> ${dest} ($*)"
    run mkdir -p "${dest}"
    for f in "$@"; do
        if [ -f "${dest}/${f}" ] && [ "${FORCE}" != "1" ]; then
            continue
        fi
        run cp -p "${src}/${f}" "${dest}/${f}"
    done
    return 0
}

# write_note <file> <text> : DNF などの記録ファイルを書く
write_note() {
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] write '$2' > $1"
        return 0
    fi
    mkdir -p "$(dirname "$1")"
    echo "$2" > "$1"
}

# ----------------------------------------------------------------------
# 手法の定義（引数は論文結果の JSON と照合済み）
#   dynamic_seq   : Proposed（逐次プルーニング）            … Fig.7 / Table 2 / Fig.11 b500
#   dynamic_par   : Proposed（並列プルーニング）            … Fig.8 / Fig.11 b1000〜2000
#   dynamic_par16 : Proposed（並列プルーニング, 16 workers） … Fig.9
#   dynamic_nopr  : Proposed（プルーニングなし）            … Table 2 / Fig.8 / Fig.9
#   static        : Static（UtilityOptimizerV2, 全時刻平均） … static_utility / average
#   adaptive      : Adapt（窓幅4, 線形 recency 重み）
# ----------------------------------------------------------------------
method_args() {
    case $1 in
        dynamic_seq)   echo "--optimization-mode dynamic --use-pruning" ;;
        dynamic_par)   echo "--optimization-mode dynamic --use-pruning --pruning-parallel" ;;
        dynamic_par16) echo "--optimization-mode dynamic --use-pruning --pruning-parallel --pruning-workers 16" ;;
        dynamic_nopr)  echo "--optimization-mode dynamic" ;;
        static)        echo "--optimization-mode static --static-timestep average --static-algorithm utility" ;;
        adaptive)      echo "--optimization-mode adaptive --window-size 4 --freq-weight linear" ;;
        *) die "未知の手法: $1" ;;
    esac
}

# result_files <method> <suffix> : staging 側の「最適化結果 ベンチマーク結果」ファイル名
result_files() {
    case $1 in
        dynamic*) echo "td_mv_optimization_result$2.json benchmark_results_dynamic$2.json" ;;
        static)   echo "static_mv_optimization_result$2.json benchmark_results_static$2.json" ;;
        adaptive) echo "adaptive_mv_optimization_result_w4$2.json benchmark_results_adaptive_w4$2.json" ;;
        *) die "未知の手法: $1" ;;
    esac
}

# run_postopt <query_set> <suffix> <method> <b_max> <dest_dir> [tag]
#   Phase 6〜9（最適化 → MV SQL → 書き換え → ベンチマーク(--ease)）を実行し、
#   最適化結果とベンチマーク結果を dest_dir へ移動する。tag はファイル名末尾に付与（例: _wo）。
run_postopt() {
    local set=$1 sfx=$2 method=$3 bmax=$4 dest=$5 tag=${6:-}
    local opt bench
    read -r opt bench <<< "$(result_files "${method}" "${sfx}")"
    local opt_dst="${opt%.json}${tag}.json"
    local bench_dst="${bench%.json}${tag}.json"

    if is_done "${dest}/${opt_dst}" "${dest}/${bench_dst}"; then
        log "SKIP（結果あり）: ${dest}/${bench_dst}"
        return 0
    fi

    local -a margs
    read -r -a margs <<< "$(method_args "${method}")"
    log "RUN post-opt: set=${set} suffix=${sfx} method=${method} B_max=${bmax}MB ${tag:+tag=${tag}}"
    protect_file "${set}" "${opt}"
    protect_file "${set}" "${bench}"
    restart_container
    run_main "${dest}/log/${method}${sfx}${tag}.log" - \
        --phase post-opt \
        --query-set "${set}" \
        --exp-suffix "${sfx}" \
        "${margs[@]}" \
        --noise-ratio 0.0 \
        --b-max "${bmax}" \
        --recalc \
        --use-docker \
        --ease \
        || die "post-opt 失敗: set=${set} suffix=${sfx} method=${method}"
    collect "${set}" "${dest}" "${opt}" "${opt_dst}"
    collect "${set}" "${dest}" "${bench}" "${bench_dst}"
    restore_file "${set}" "${opt}"
    restore_file "${set}" "${bench}"
}

# run_phase6 <query_set> <suffix> <method> <b_max> <dest_dir> <tag> [timeout|-]
#   最適化（Phase 6）のみ実行（DB 不要）。最適化結果を dest_dir へ移動する。
#   戻り値: 0 = 成功またはスキップ、124 = タイムアウト、その他 = 失敗
run_phase6() {
    local set=$1 sfx=$2 method=$3 bmax=$4 dest=$5 tag=$6 to=${7:--}
    local opt _bench
    read -r opt _bench <<< "$(result_files "${method}" "${sfx}")"
    local opt_dst="${opt%.json}${tag}.json"

    if is_done "${dest}/${opt_dst}"; then
        log "SKIP（結果あり）: ${dest}/${opt_dst}"
        return 0
    fi

    local -a margs
    read -r -a margs <<< "$(method_args "${method}")"
    log "RUN phase6: set=${set} suffix=${sfx} method=${method} B_max=${bmax}MB tag=${tag} timeout=${to}"
    protect_file "${set}" "${opt}"
    run_main "${dest}/log/phase6_${method}${sfx}${tag}.log" "${to}" \
        --phase 6 \
        --query-set "${set}" \
        --exp-suffix "${sfx}" \
        "${margs[@]}" \
        --b-max "${bmax}" \
        --recalc
    local status=$?
    if [ ${status} -ne 0 ]; then
        # タイムアウト等で途中の出力が無ければ元ファイルを戻す（あれば EXIT 時に警告）
        restore_file "${set}" "${opt}"
        return ${status}
    fi
    collect "${set}" "${dest}" "${opt}" "${opt_dst}"
    restore_file "${set}" "${opt}"
}
