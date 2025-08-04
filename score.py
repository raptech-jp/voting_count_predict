# score_seats.py
import json, math, os, sys
from typing import Dict, List, Tuple

# ==== 設定 ============================================================
OFFICIAL_JSON = "councillors2025.json"  # 公式データ
KEY_SEATS = "seats_by_party"
KEY_TOTAL = "total_seats"
USE_RICH = True
SORT_BY = "weighted_error"               # "weighted_error" | "abs_error" | "official_asc"
ALLOW_USER_MISMATCH = False              # True: 合計不一致でも採点続行（警告のみ）

# --- スコア関数設定 ---
SCORE_MODE = "exp"                       # "linear" | "exp"
EXP_HALFLIFE = 5.0                       # 指数型の半減点: WMAE=HALFLIFE で 50点（推奨: 4〜8）
# ======================================================================

# 例: ユーザー入力（外部ファイルから読み込む場合は差し替え）
user_input: Dict[str, int] = {
    "Liberal_Democratic_Party": 78,
    "Komeito": 21,
    "Constitutional_Democratic_Party": 60,
    "Democratic_Party_For_the_People": 27,
    "Japan_Innovation_Party": 11,
    "Party_of_Do_It_Yourself": 16,
    "Japanese_Communist_Party": 8,
    "Reiwa_Shinsengumi": 6,
    "Social_Democratic_Party": 2,
    "Conservative_Party_of_Japan": 2,
    "NHK_Party": 1,
    "Team_Mirai": 1,
    "Independents": 15
}

def load_official(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if KEY_SEATS not in data or not isinstance(data[KEY_SEATS], dict):
        raise ValueError(f"JSONに '{KEY_SEATS}' が見つからないか形式が不正です")
    if KEY_TOTAL not in data or not isinstance(data[KEY_TOTAL], int):
        raise ValueError(f"JSONに '{KEY_TOTAL}' が見つからないか形式が不正です")

    seats = {k: int(v) for k, v in data[KEY_SEATS].items()}
    total_from_json = int(data[KEY_TOTAL])
    house = data.get("house", "")
    election_date = data.get("election_date", "")

    # 非負チェック
    for k, v in seats.items():
        if v < 0:
            raise ValueError(f"公式データに負の値: {k}={v}")

    return seats, total_from_json, house, election_date

def sums(official: Dict[str, int], pred: Dict[str, int]) -> Tuple[int, int]:
    off_sum = sum(int(v) for v in official.values())
    pred_sum = sum(int(max(0, v)) for v in pred.values())  # 負は0に丸める
    return off_sum, pred_sum

def validate_totals(official: Dict[str, int], total_declared: int, pred: Dict[str, int]) -> Tuple[bool, List[str]]:
    msgs = []
    ok = True
    off_sum, pred_sum = sums(official, pred)

    if off_sum != total_declared:
        ok = False
        msgs.append(f"[公式合計不一致] JSON total_seats={total_declared} だが seats_by_party 合計={off_sum}")

    if pred_sum != total_declared:
        msg = f"[ユーザー合計不一致] 予測合計={pred_sum} ／ 要求合計={total_declared}"
        if ALLOW_USER_MISMATCH:
            msgs.append("⚠ " + msg + "（警告：採点は続行）")
        else:
            ok = False
            msgs.append(msg + "（エラー：採点中止）")
    return ok, msgs

def calc_score(wmae: float, S: int) -> float:
    """
    スコア(0–100)。SCORE_MODEにより変換。
    - linear: 100 - 100*(WMAE/S)  従来型（甘め）
    - exp   : 100 * exp(-k * WMAE)  半減点EXP_HALFLIFEでスコア半減
    """
    if SCORE_MODE == "linear":
        return max(0.0, 100.0 - 100.0 * (wmae / max(1, S)))
    elif SCORE_MODE == "exp":
        # k = ln(2) / HALFLIFE → WMAE=HALFLIFE でスコアが 100→50 に半減
        k = math.log(2.0) / max(1e-9, EXP_HALFLIFE)
        return 100.0 * math.exp(-k * wmae)
    else:
        return max(0.0, 100.0 - 100.0 * (wmae / max(1, S)))

def compute_rows(official: Dict[str, int], pred: Dict[str, int]):
    parties = list(official.keys())
    unknown_pred = [p for p in pred.keys() if p not in official]
    missing_pred = [p for p in parties if p not in pred]

    rows = []
    sum_w = 0.0
    sum_werr = 0.0

    for party in parties:
        y = int(official.get(party, 0))
        yhat = int(max(0, pred.get(party, 0)))  # 負は0に丸める
        diff = yhat - y
        abs_err = abs(diff)
        w = 1.0 / math.sqrt(y + 1)            # 小党ほど重み大
        werr = abs_err * w
        rows.append({
            "party": party,
            "official": y,
            "pred": yhat,
            "diff": diff,
            "abs_error": abs_err,
            "weight": w,
            "weighted_error": werr
        })
        sum_w += w
        sum_werr += werr

    # 指標
    S = sum(official.values()) or 1
    wmae = (sum_werr / sum_w) if sum_w > 0 else 0.0
    score = calc_score(wmae, S)

    # 並び順
    if SORT_BY == "weighted_error":
        rows.sort(key=lambda r: r["weighted_error"], reverse=True)
    elif SORT_BY == "abs_error":
        rows.sort(key=lambda r: r["abs_error"], reverse=True)
    elif SORT_BY == "official_asc":
        rows.sort(key=lambda r: r["official"])

    return rows, wmae, score, S, unknown_pred, missing_pred

def print_plain_header(house: str, date: str):
    title = f"=== 議席予測スコア（{house or '-'} / {date or '-'}）===\n"
    print(title)

def print_table_plain(rows, wmae, score, S, unknown_pred, missing_pred, total_msgs):
    if unknown_pred:
        print(f"※ 公式データに無い政党（採点対象外）: {', '.join(unknown_pred)}")
    if missing_pred:
        print(f"※ 入力が無い政党は0扱い: {', '.join(missing_pred)}")
    for msg in total_msgs:
        print(msg)

    print()
    h = f"{'Party':36} {'Official':>8} {'Pred':>6} {'Diff':>6} {'Abs':>5} {'Weight':>8} {'W-Err':>8}"
    print(h)
    print("-" * len(h))
    for r in rows:
        diff = r["diff"]
        sign = "+" if diff > 0 else ("" if diff == 0 else "-")
        diff_str = f"{sign}{abs(diff)}"
        print(f"{r['party'][:36]:36} {r['official']:>8} {r['pred']:>6} {diff_str:>6} "
              f"{r['abs_error']:>5} {r['weight']:>8.3f} {r['weighted_error']:>8.3f}")

    print("\n-- Summary --")
    print(f"Total seats (S) : {S}")
    print(f"WMAE            : {wmae:.4f}")
    print(f"Score ({SCORE_MODE}) : {score:.2f}")
    if SCORE_MODE == "exp":
        print(f"(Half-life = {EXP_HALFLIFE}, k = ln(2)/Half-life = {math.log(2.0)/EXP_HALFLIFE:.4f})")

def print_rich(rows, wmae, score, S, unknown_pred, missing_pred, total_msgs, house, date):
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
        from rich.panel import Panel
        from rich.text import Text
    except ImportError:
        return False

    console = Console()
    console.print()
    subtitle = f"{house or '-'} / {date or '-'}"
    console.print(Panel.fit(f"議席予測スコア [bold](小党重み付きMAE → {SCORE_MODE})[/bold]\n{subtitle}", style="bold cyan"))

    if unknown_pred:
        console.print(f"[yellow]※ 公式データに無い政党（採点対象外）: {', '.join(unknown_pred)}[/yellow]")
    if missing_pred:
        console.print(f"[yellow]※ 入力が無い政党は0扱い: {', '.join(missing_pred)}[/yellow]")
    for msg in total_msgs:
        style = "green" if "OK" in msg else "red"
        console.print(f"[{style}]{msg}[/{style}]")
    console.print()

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Party", style="white", no_wrap=True)
    table.add_column("Official", justify="right")
    table.add_column("Pred", justify="right")
    table.add_column("Diff", justify="right")
    table.add_column("Abs", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("W-Err", justify="right")

    for r in rows:
        diff = r["diff"]
        diff_str = f"{diff:+}"
        diff_style = "green" if diff == 0 else ("red" if diff > 0 else "blue")
        table.add_row(
            r["party"],
            str(r["official"]),
            str(r["pred"]),
            f"[{diff_style}]{diff_str}[/{diff_style}]",
            str(r["abs_error"]),
            f"{r['weight']:.3f}",
            f"{r['weighted_error']:.3f}",
        )

    console.print(table)
    console.print()
    summary = Table(box=box.MINIMAL_DOUBLE_HEAD)
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Total seats (S)", str(S))
    summary.add_row("WMAE", f"{wmae:.4f}")
    summary.add_row(f"Score ({SCORE_MODE})", f"{score:.2f}")
    if SCORE_MODE == "exp":
        summary.add_row("Half-life", f"{EXP_HALFLIFE}")
        summary.add_row("k", f"{math.log(2.0)/EXP_HALFLIFE:.4f}")
    console.print(summary)
    console.print()
    return True

def main():
    try:
        official, total_declared, house, election_date = load_official(OFFICIAL_JSON)
    except Exception as e:
        print(f"[Error] 公式データの読み込みに失敗: {e}", file=sys.stderr)
        sys.exit(1)

    ok, total_msgs = validate_totals(official, total_declared, user_input)
    used_rich = False
    if USE_RICH:
        used_rich = print_rich([], 0, 0, sum(official.values()), [], [], total_msgs, house, election_date)
    if not used_rich:
        print_plain_header(house, election_date)
        for msg in total_msgs:
            print(msg)
        print()

    if not ok and not ALLOW_USER_MISMATCH:
        if not used_rich:
            print("[終了] 合計不一致のため採点を中止しました。", file=sys.stderr)
        sys.exit(2)

    rows, wmae, score, S, unknown_pred, missing_pred = compute_rows(official, user_input)

    if USE_RICH:
        used_rich = print_rich(rows, wmae, score, S, unknown_pred, missing_pred, total_msgs, house, election_date)
    if not used_rich:
        print_table_plain(rows, wmae, score, S, unknown_pred, missing_pred, total_msgs)

if __name__ == "__main__":
    main()
