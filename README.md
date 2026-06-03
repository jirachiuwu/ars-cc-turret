# ars-cc-turret

**Ars Nouveau × ComputerCraft の自動照準・偏差射撃タレット（対地対空 CIWS）。**

Ars Nouveau の Rotating Spell Turret を継承し、ComputerCraft から「手足」として操作できるタレット。標的の検出・偏差（リード）計算・追従発射の**頭脳は全部 Lua**。Java は列挙・照準・発射の口を開けるだけ。動く標的の未来位置を `P + V·(dist/s)` で先回りして撃つ。

- MC **1.20.1 / Forge**
- 依存: **Ars Nouveau**, **CC: Tweaked**（+ Ars の依存 Curios / GeckoLib / MixinExtras）

---

## 何ができる

- 範囲内のエンティティを位置・速度つきで検出し、**動く標的を偏差撃ち**（地上・空中・全方位）
- 標的優先を **最寄り(nearest) / 接近脅威優先(fastestClose)** から選択（実行時切替）
- **壁越し・地下は撃たない**（視線判定）／**レッドストーンでは誤射しない**（操作は CC のみ）
- マナ消費・連射ガード（1tick1発）
- **CC モニターに火器管制表示**：状態・標的・偏差解・設定・「計算して撃つ」ログを 20Hz で。タップで設定切替

## 使い方（ゲーム内）

1. **`CC Turret` ブロックを設置**し、隣に **ComputerCraft のコンピュータ**を密着（または有線モデムで接続）。見やすくするなら **Monitor** も隣に。
2. タレットに **Projectile から始まる攻撃スペル**（例: Projectile → Harm）を書いた **Spell Parchment を右クリックで装填**（vanilla の Ars スペルタレットと同じ）。
3. コンピュータで一式をインストール（http が有効な環境）:
   ```
   wget run https://raw.githubusercontent.com/jirachiuwu/ars-cc-turret/main/lua/install.lua
   ```
4. 起動:
   ```
   main
   ```
   （`install` は `startup.lua` も作るので、以後は再起動で自動再開）

### 操作・設定

- モニターの **`[PRIO]`** タップ … 最寄り ⇄ 接近脅威優先
- モニターの **`[CRE]`** タップ … クリエイティブ（マナ源なしでも撃つ）ON/OFF
- 既定値は `config.lua`、実行時の変更は CC `settings`(`.turret`) に永続化
- マナ源が無い実戦運用では近くに **Source Jar 等**を置くか `[CRE]` を ON に

## 仕組み（二階建て）

```
main.lua → turret.lua(火器管制1step) → targeting.lua(標的選択) / ballistics.lua(偏差解)
                                      → monitor.lua(表示)
毎tick: P.listEntities() → 標的選択 → lead(muzzle,P,V,s) → P.aim() → 収束したら P.fire()
```

- **Java（手足）**: 範囲内エンティティの事実列挙、小数座標→照準角、発射の正規ルート（弾速可変）、redstone/連射/マナの機械ガード。`TurretPeripheral` が `@LuaFunction` で口を開ける。
- **Lua（頭脳）**: 標的選択・偏差計算・発射判断・表示。
- 弾速 `s`[blocks/tick] = 実弾速（同一フィールド由来）なので `t = dist/s` が物理と厳密一致 = 命中精度の核。

詳細設計は [`docs/design.md`](docs/design.md)。

## ビルド

```
./gradlew build
```
`build/libs/` に jar。MC 1.20.1 Forge + Ars Nouveau + CC: Tweaked の環境へ。

## テスト（ゲーム不要・機械検証）

- `python lua/ballistics_test.lua` 相当は lupa 経由（`pip install lupa`）。
- `python lua/targeting_test.py` … 標的優先則。
- `python lua/app_test.py` … 全 lua 構文 + `turret.step` 状態機械/ログ + `monitor.render`（本物の Lua を lupa で実行）。

## ライセンス / クレジット

タレットの見た目は依存先 **Ars Nouveau** の spell turret アセット（geo/texture/animation）を参照。
