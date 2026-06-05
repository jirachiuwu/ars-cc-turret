# CLAUDE.md — 案件: CC連携 自動照準・偏差射撃タレット (ars-cc-turret)

この案件専用のルール。SOLIS の核(D:/SOLIS/CLAUDE.md)が土台。ここは案件固有の前提だけを足す。

## 何を作るか
Ars Nouveau の Rotating Spell Turret を継承し、CC:Tweaked から操作する対空タレット MOD。
頭脳(標的選択・偏差計算・発射判断)は**全部 Lua**。Java は「事実を返す/指示を実行する」手足に徹する。
弾速を peripheral フィールド化して Lua の偏差計算と実弾速を厳密一致させ命中精度を担保する。

## 技術スタック(確定・現物確認済み)
- MC 1.20.1 / Forge 47.2.0 / JDK17 / official mappings
- Ars Nouveau 4.12.7(CurseMaven projectId=401955, fileId=6688854。fg.deobf でラップ必須)
- CC:Tweaked 1.116.1(forge)。modid は `computercraft`
- GeckoLib 4.4.4(継承surfaceに露出するので compile 必須)
- 土台: D:/Claude/ars-no-iframes を複製(build.gradle/gradlew/gradle.properties 流用)
- mod_id=arsccturret / package=com.yui.arsccturret
- 実ソース: D:/Claude/ars-cc-turret/refs/(ars_nouveau/ と adams/)。設計はここで裏取り済み

## 前提(覆さない・合意済み)
1. 継承元は RotatingSpellTurret / RotatingTurretTile。AN本体のみ compile依存。Adam's には依存しない(参考のみ・バグ持ち)
2. 効果(Effect)・VFX・トレイル・衝突は AN純正 EntityProjectileSpell + resolver に委譲。自前実装は弾速可変の一点だけ
3. 偏差は Lua側。未来位置 = 現在位置 + 速度ベクトル × 弾到達時間(t = dist / s)
4. 単位は全て blocks/tick(秒ではない)。20倍ズレたらまず単位を疑う
5. 初版スコープ = Projectile 1発命中まで。否定リスト(design.md §11)に手を出さない

## ビルド / 検証コマンド
```
# コンパイル(機械で白黒。最初にやる)
& 'D:\Claude\ars-cc-turret\gradlew.bat' --no-daemon --refresh-dependencies compileJava
# 実機(client起動)
& 'D:\Claude\ars-cc-turret\gradlew.bat' --no-daemon runClient
# Lua偏差の純粋テスト(ゲーム不要)
lua ballistics_test.lua   # or craftos-pc
```
検証は段0(Lua純テスト)→段1a(空継承Probe)→段1b(実体)→段1.5(peripheral1メソッド/スレッド)→段2(委譲)→段2.5(往復恒等)→段3(偏差)→段4(スレッド/連射/redstone)の順。各段は機械で白黒つくか目視1発。

## やってはダメ リスト(地雷・実ソースで確認済み)
- ❌ `rotationX/Y` `neededRotationX/Y` `clientNeededX/Y` を tile で**再宣言**する(Adam's の field shadowing。親フィールドを使え)
- ❌ 3引数 `tick(Level,BlockState,BlockPos)` を override する(無引数 `tick()` が死ぬ。生命線)
- ❌ `tick()` override で `super.tick()` を呼び忘れる(親の旋回補間が死ぬ)
- ❌ `setPlacedBy` `getShootAngle` `orderedByNearest` `getDispensePosition` を override する(親の正しい実装を壊す)
- ❌ `getShootAngle()`("pure luck"式)を「修正」する(整合一式。触るな)
- ❌ `aimVec` で毎tick `updateBlock()` を呼ぶ(パケットスパム。`setChanged()` のみ)
- ❌ CurseForge の `-all.jar` を flatDir で直接 compile 依存にする(SRG名でリンク不能。fg.deobf 必須)
- ❌ build.gradle の repositories から `mavenCentral()` / Forge maven を落とす(推移依存が解決できずビルドが落ちる)
- ❌ world走査 read を `@LuaFunction` 素で書く(別スレ実行でクラッシュ。`mainThread=true` 必須)
- ❌ 自前 executeBlocking / volatile 退避機構を発明する(CC公式 `@LuaFunction(mainThread=true)` を使え)
- ❌ redstone 発射経路(Block#tick / neighborChanged)を放置する(CC主役が破れる。空 override で塞ぐ)
- ❌ getSource() で全ジャー合算を返す(SourceUtil は単一プロバイダ充足。合算すると空撃ちループ)
- ❌ Lua偏差で config.speed を直読みする(クランプ後の `P.getProjectileSpeed()` を読め)
- ❌ canFire / autonomous / Touch / 接近速度優先 を初版で実装する(否定リスト §11)
- ❌ 効果が乗らないとき onCast を魔改造する(本体 shootSpell と引数1対1照合が先)

## 進め方
- 設計・実装は「動く証拠」とセットで報告。自己申告(作りました/PASS)は受け付けない
- 機械で白黒つくこと(コンパイル/テスト)は自分で直し続ける。聞くな
- 機械で出ないこと(この設計でいいか)は一回ゆいくんに見せて決めてもらう
- 設計図(design.md)を育てる。コードは設計図から作り直せる。身軽に捨てる

## 動かす前のチェック(育つチェックリスト・案件固有)
- **Java→Lua フィールド名突合**: 実機で動かす前に、`m.put("KEY", ...)` で put してるキー名と Lua側 `tgt.KEY` 参照名を grep で突合する。命名がズレてると Lua側の `or` フォールバックで握りつぶされ、**「直線運動ですら当たらない」型の沈黙バグ**になる。
  - 由来: 2026-06-05 §12.19 CT実装時、Java で `tCenter` put / Lua で `dtCenter` 参照 → dtCenter が常に 0 で標本平均位置(数tick前)から狙ってしまい実機で外す。ハーネスは Python が dtCenter を自前計算してたので 20 PASS してたのに実機で外した(ハーネスの設計欠陥)。
  - 対策: ハーネスで「Java→Lua受け渡し経路を Python が代行」せず、実 Java の戻りキーに揃えて検証する。put キー一覧と Lua tgt 参照一覧の集合差分が空かを grep で確認してから実機投入。
- **合成シナリオの前提が実機標的の物理特性に合うか確認**: 「等速・等ω」を仮定するモデル(CT等)は、実機標的(エリトラ等)がその仮定を満たさない場合、合成PASS でも実機FAIL。設計確定前に「実標的の運動特性が仮定を満たすか」を1回確認。
  - 由来: 2026-06-06 §12.20 CT撤退。CTモデルは「等速で同じ弧」前提だが、実エリトラはローカルな進行方向ヨレを含む。lsq の heading差分でω推定が暴れ、ω·t_flight が大きくなって「半周回った真逆」を撃つ事故が頻発。クランプ追加でも改善せず実機で CV > CT (-1.9pt) と判定、default OFF へ。
  - 対策: 標的タイプごとに「運動の物理特性」を1度確認(等速か、等ωか、ジグザグか)。合成シナリオを実機標的に寄せる。`turret.csv` ログを実機シナリオとしてハーネスに統合(ct_harness_test.py シナリオ8)。
