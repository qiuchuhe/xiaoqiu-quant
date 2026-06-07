#!/bin/bash
# ====================================================
# A股实时行情看板  --  curl + bash, 无 Python 依赖
# ====================================================
# 用法:
#   ./stock_watch.sh              涨跌前15
#   ./stock_watch.sh -w            自选股
#   ./stock_watch.sh -t 20         涨幅前20
#   ./stock_watch.sh -d 15         跌幅前15
#   ./stock_watch.sh -r 5          每5秒刷新
#   ./stock_watch.sh -c 600519     查单个股票
# ====================================================

set -e

# ---- 颜色 ----
R='\033[1;31m'  # 红涨
G='\033[1;32m'  # 绿跌
Y='\033[1;33m'  # 黄
C='\033[1;36m'  # 青
W='\033[1;37m'  # 白
D='\033[2;37m'  # 灰
Z='\033[0m'     # 重置

# ---- 自选股 ----
WATCHLIST=(
    "000001:平安银行"  "600519:贵州茅台"  "300750:宁德时代"
    "000858:五粮液"    "601012:隆基绿能"  "002594:比亚迪"
    "600036:招商银行"  "300059:东方财富"
)

# ---- 参数 ----
WATCH=0; TOP=0; DROP=0; REFRESH=0; CODE=""
while getopts "wt:d:r:c:h" opt; do
    case $opt in
        w) WATCH=1 ;;
        t) TOP=$OPTARG ;;
        d) DROP=$OPTARG ;;
        r) REFRESH=$OPTARG ;;
        c) CODE=$OPTARG ;;
        h) echo "用法: $0 [-w] [-t N] [-d N] [-r N] [-c CODE]"; exit 0 ;;
    esac
done

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
REFERER="https://quote.eastmoney.com/"
TIMEOUT=8

# ---- 数据获取 ----

fetch_json() {
    # $1 = URL, 返回 JSON 到 stdout
    curl -s --connect-timeout "$TIMEOUT" \
        -H "User-Agent: $UA" \
        -H "Referer: $REFERER" \
        "$1" 2>/dev/null
}

fetch_index() {
    local url="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=1&np=1&fltt=2&invt=2&fid=f3&fs=b:MK0010,b:MK0004,b:MK0007&fields=f2,f3,f4,f12,f14"
    fetch_json "$url"
}

fetch_stocks() {
    local fields="f2,f3,f4,f5,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f124"
    local url="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5000&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=${fields}"
    fetch_json "$url"
}

# ---- JSON 解析 (轻量, 不用 jq) ----

parse_stocks() {
    # 从 JSON 提取股票数据，输出 TSV 格式
    python3 -c "
import sys, json
data = json.load(sys.stdin)
diffs = data['data']['diff']
for r in diffs:
    print('\t'.join(str(r.get(k, '')) for k in [
        'f12','f14','f2','f3','f4','f5','f6','f8','f9','f15','f16','f17','f18'
    ]))
" 2>/dev/null
}

parse_index() {
    python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data['data']['diff']:
    print(f\"{r['f14']}\t{r.get('f2','')}\t{r.get('f3','')}\t{r.get('f4','')}\")
" 2>/dev/null
}

# ---- 显示 ----

color_price() {
    # $1=price $2=preclose
    local p="$1" pc="$2"
    if [ -z "$pc" ] || [ "$pc" = "None" ] || [ "$pc" = "-" ] || [ "$pc" = "0" ]; then
        printf "%7s" "$p"
    elif [ "$(echo "$p >= $pc" | bc 2>/dev/null || echo 0)" = "1" ]; then
        printf "${R}%7s${Z}" "$p"
    else
        printf "${G}%7s${Z}" "$p"
    fi
}

color_pct() {
    local v="$1"
    if [ -z "$v" ] || [ "$v" = "-" ] || [ "$v" = "None" ]; then
        printf "${D}%9s${Z}" "--"
    elif [ "$(echo "$v > 0" | bc 2>/dev/null || echo 0)" = "1" ]; then
        printf "${R}%+8.2f%%${Z}" "$v"
    elif [ "$(echo "$v < 0" | bc 2>/dev/null || echo 0)" = "1" ]; then
        printf "${G}%+8.2f%%${Z}" "$v"
    else
        printf "${D}%+8.2f%%${Z}" "$v"
    fi
}

show() {
    clear 2>/dev/null || true

    # 取数据
    local idx_json stock_json
    idx_json=$(fetch_index)
    stock_json=$(fetch_stocks)

    if [ -z "$idx_json" ] || [ -z "$stock_json" ]; then
        echo -e "${R}[!] 数据获取失败, 请检查网络${Z}"
        return 1
    fi

    # 解析指数
    local idx_data
    idx_data=$(echo "$idx_json" | parse_index)

    # 显示指数头
    echo ""
    local parts=()
    while IFS=$'\t' read -r name price pct chg; do
        local c="$W" a="—"
        if [ -n "$pct" ] && [ "$pct" != "None" ] && [ "$pct" != "-" ]; then
            if [ "$(echo "$pct > 0" | bc 2>/dev/null || echo 0)" = "1" ]; then c="$R"; a="▲"; fi
            if [ "$(echo "$pct < 0" | bc 2>/dev/null || echo 0)" = "1" ]; then c="$G"; a="▼"; fi
            parts+=("${C}${name}${Z} ${c}${price}  ${a} ${pct:0:6}%${Z}")
        fi
    done <<< "$idx_data"
    echo -e "  $(IFS='  |  '; echo "${parts[*]}")"
    echo ""

    # 解析个股
    local tmpfile
    tmpfile=$(mktemp)
    echo "$stock_json" | parse_stocks > "$tmpfile"

    # 筛选排序
    local display_file
    display_file=$(mktemp)

    if [ -n "$CODE" ]; then
        CODE=$(printf "%06d" "$CODE" 2>/dev/null || echo "$CODE")
        grep "^${CODE}" "$tmpfile" > "$display_file" 2>/dev/null || true
        local title="查询: $CODE"
    elif [ "$WATCH" = "1" ]; then
        > "$display_file"
        for entry in "${WATCHLIST[@]}"; do
            local wcode="${entry%%:*}"
            grep "^${wcode}" "$tmpfile" >> "$display_file" 2>/dev/null || true
        done
        local title="自选股"
    elif [ "$TOP" -gt 0 ]; then
        sort -t$'\t' -k4 -nr "$tmpfile" | head -n "$TOP" > "$display_file"
        local title="涨幅 Top $TOP"
    elif [ "$DROP" -gt 0 ]; then
        sort -t$'\t' -k4 -n "$tmpfile" | head -n "$DROP" > "$display_file"
        local title="跌幅 Top $DROP"
    else
        # 涨15 + 跌15
        sort -t$'\t' -k4 -nr "$tmpfile" | head -n 15 > "$display_file"
        sort -t$'\t' -k4 -n "$tmpfile" | head -n 15 >> "$display_file"
        sort -u -t$'\t' -k1,1 "$display_file" -o "$display_file"
        local title="涨幅前15 + 跌幅前15"
    fi

    local count
    count=$(wc -l < "$display_file" 2>/dev/null || echo 0)

    # 画表格
    echo -e "  ${C}${title}${Z}  (${count} 只)"
    echo    "  ────────────────────────────────────────────────────────────────────────────────"
    printf  "  %-8s %-10s %7s  %9s  %6s  %6s  %9s\n" \
            "代码" "名称" "最新价" "涨跌幅" "换手%" "PE" "成交额(亿)"
    echo    "  ────────────────────────────────────────────────────────────────────────────────"

    local up_n=0 dn_n=0
    while IFS=$'\t' read -r code name price pct chg vol amt turn pe high low open preclose; do
        [ -z "$code" ] && continue

        # 涨跌统计
        if [ -n "$pct" ] && [ "$pct" != "-" ] && [ "$pct" != "None" ]; then
            if [ "$(echo "$pct > 0" | bc 2>/dev/null || echo 0)" = "1" ]; then ((up_n++)); fi
            if [ "$(echo "$pct < 0" | bc 2>/dev/null || echo 0)" = "1" ]; then ((dn_n++)); fi
        fi

        # 成交额转亿
        local amt_e
        amt_e=$(echo "scale=1; ${amt:-0} / 100000000" | bc 2>/dev/null || echo "0")

        printf "  ${C}%-8s${Z} %-10s %s  %s  %6.2f%%  %6.1f  %8.1f\n" \
            "$code" "${name:0:10}" \
            "$(color_price "${price:-0}" "${preclose:-0}")" \
            "$(color_pct "${pct:-0}")" \
            "${turn:-0}" "${pe:-0}" "$amt_e"
    done < "$display_file"

    echo "  ────────────────────────────────────────────────────────────────────────────────"
    local now
    now=$(date '+%H:%M:%S')
    echo -e "  ${D}${now}  |  涨 ${R}${up_n}${D}  跌 ${G}${dn_n}${D}  |  Ctrl+C 退出${Z}"
    echo ""

    rm -f "$tmpfile" "$display_file"
}

# ---- 主流程 ----

if [ "$REFRESH" -gt 0 ]; then
    echo -e "\n  ${Y}每 ${REFRESH}s 自动刷新, Ctrl+C 退出${Z}"
    while true; do
        show || true
        sleep "$REFRESH"
    done
else
    show
    echo -e "  ${D}Tip: ./stock_watch.sh -r 5   (每5秒自动刷新)${Z}"
    echo ""
fi
