# このプロジェクトについて
選挙をネタにしたゲームを作りたい。
政党別獲得議席を予想して、その差分を如何に抑えられるかを競う。政党の規模によって議席の重みが違うので、それもスコアに反映予定。

# スコアの計算式について

## 実際の議席数（公式データ）と予測値の差

$$
\text{diff}_i = \hat{y}_i - y_i
$$

$$
\text{abs\_error}_i = |\text{diff}_i|
$$

## 小党重視の重み付け

$$
\text{weight}_i = \frac{1}{\sqrt{y_i + 1}}
$$

$$
\text{weighted\_error}_i = \text{abs\_error}_i \times \text{weight}_i
$$

## 全体の重み付き平均誤差（WMAE）

$$
\text{WMAE} = \frac{\sum_i \text{weighted\_error}_i}{\sum_i \text{weight}_i}
$$


## スコア（0〜100点）

### モード1: 線形スコア（`linear`）

$$
\text{Score}_{\text{linear}} = \max\left(0, 100 - 100 \times \frac{\text{WMAE}}{S}\right)
$$

ここで $S$ は総議席数です。

### モード2: 指数スコア（`exp`）

$$
k = \frac{\ln(2)}{\text{HALFLIFE}}
$$

$$
\text{Score}_{\text{exp}} = 100 \times e^{-k \times \text{WMAE}}
$$

* HALFLIFE: 誤差がこの値のときスコアがちょうど半分（50点）になるよう調整
* 例えば `EXP_HALFLIFE = 5.0` の場合、

$$
k = \frac{\ln(2)}{5.0} \approx 0.1386
$$

