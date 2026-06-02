# Workflow Extras (一時)

## knownIssues (実機検証項目)
- 弾速 s の安全上限(トンネリング境界)。目安 0.05〜2.5、>~3 blocks/tick で薄い標的をすり抜ける可能性。実機で計測して SPEED_MAX を確定する
- 近接×高弾速での自爆条件。弾は砲口=ブロック中心+0.5·照準ベクトルからスポーンするので、s が大きいと1tick目で隣接ブロック/自タレットへ即着弾しうる。理論上 s>~0.5 で際を越えるが、実際の自爆境界を目視で確認
- @LuaFunction(mainThread=true) で world走査 read のブロッキング戻り値が Lua に正しく返るか。CC 1.116.1 でクラッシュせず table が返ることを段1.5で確認
- @LuaFunction の Map<Integer,Map<String,Object>> が CC 1.116.1 で Lua 配列(ipairs可)になるか。最小 getTest()->Map.of(1,a,2,b) で確認
- タレット2台に別コンピュータから同時アクセスしてクラッシュ(ConcurrentModificationException)しないこと(段4)
- aimVec の角度逆算式と getShootAngle('pure luck'式)が厳密な逆関数か。静止標的に aim(P)→収束→fire で P に当たるか(往復恒等性・段2.5)。許容外なら aimTolDeg を詰めるか aim ベクトル直渡し変種に切替
- 効果/VFX が resolver 経由で乗るか(静止羊に Harm を1発・段2)。乗らなければ TileCaster/SpellContext/FakePlayer 引数を本体 shootSpell と1対1照合
- 偏差 t=dist/s が物理と一致するか(動く豚に現在位置狙いで外れ・未来位置狙いで当たる・段3)。外れたらまず単位(tick vs 秒)を疑う
- redstone 信号を隣に与えても発射しないこと(Block#tick/neighborChanged 封鎖の確認・段4)
- プレイヤーの server側 getDeltaMovement 精度(移動パケット由来でズレ得る)。対プレイヤー偏差が要件なら前tick位置差分フォールバックが必要。初版は対Mobスコープ
- CurseMaven fileId(6688854)=4.12.7-all が解決するか。GeckoLib cloudsmith URL が落ちていないか(modmaven.dev 退避路)。Patchouli/Curios/JEI を runtimeOnly に足す必要が runClient 完全起動で出るか
- AllTheMods 同梱 CC の実 modid(computercraft)と実ビルド番号を /mods で突合し mods.toml の versionRange を確定。同梱版がビルド番号違いだと mandatory 依存ロード拒否で本体起動しない
- peripheral 接続断(tile破壊後の wrap 参照)の挙動。破壊→再 wrap でエラーにならないか
- GeckoLib animation.json に 'recoil' クリップが無いと walkPredicate が例外を投げないか(最小空クリップで回避できるか)
- GeoBlockRenderer 未登録だと設置時にブロック不可視/クラッシュしないか。初版は無回転最小描画で段2に入れるか
- SourceUtil の単一プロバイダ供給判定API名(AN 4.12.7 実jar)。luaMaxSingleSource を正しく実装できるAPIがあるか、無ければ takeSource ドライラン相当を自前評価

## firstVerification (最初の機械検証手順)
段0と段1aを並行で回す。これが最初の機械検証(全て白黒つく)。

【段0: Lua偏差の純粋テスト(ゲーム不要・即回る)】
1. design.md §3.2 の ballistics.lua と §3.6 の assert テストを ballistics_test.lua に書く。
2. 既知 (T,P,V,s) 複数ケース + クランプ境界ケース(s=0.04→0.05, s=3.0→2.5 を丸めてから lead に渡す)で実行:
   `lua ballistics_test.lua`(または craftos-pc)
3. 全ケースで `len(bullet-target) < 0.5` が通れば偏差の核は固い。通らなければ maxIter / escapes 閾値を調整して再実行(自分で直し続ける)。

【段1a: 空継承 Probe(最恐核心=deobf remap を単独分離)】
1. 土台を複製: D:/Claude/ars-no-iframes → D:/Claude/ars-cc-turret(build.gradle/gradlew/gradle/wrapper/settings.gradle 流用)。
2. build.gradle の repositories を design.md §4.2 に置換(★mavenCentral() と Forge maven を必ず含める。推移依存の解決先)。dependencies を §4.3 に置換(Ars/GeckoLib/CC を fg.deobf)。gradle.properties に §4.4 を追記(mod_id=arsccturret, gecko_version=4.4.4, cct_version=1.116.1)。
3. src/main/java/com/yui/arsccturret/ に1ファイルだけ置く:
   `package com.yui.arsccturret; import com.hollingsworth.arsnouveau.common.block.RotatingSpellTurret; public class Probe extends RotatingSpellTurret {}`
4. コンパイル:
   `& 'D:\Claude\ars-cc-turret\gradlew.bat' --no-daemon --refresh-dependencies compileJava`
5. 判定:
   - `BUILD SUCCESSFUL` + build/classes/java/main/com/yui/arsccturret/Probe.class 生成 = 依存解決+継承+SRG→official remap+推移依存が全部緑。最恐リスク消滅。段1bへ。
   - `Could not resolve …slf4j/commons/cobalt` = repositories に mavenCentral()/Forge maven が無い(§4.2へ)。
   - `package com.hollingsworth.arsnouveau… does not exist` = CurseMaven 座標/URLミス。
   - `cannot find symbol: method m_xxxxx_` = fg.deobf 未適用 → --refresh-dependencies 再実行 or ~/.gradle/caches/forge_gradle/deobf 削除。
   - `package software.bernie.geckolib does not exist` = GeckoLib repo を modmaven.dev 退避路へ切替。

段0(Lua)と段1a(継承コンパイル)が両方緑になったら、段1b(CCTurret/CCTurretTile 実体を足して再コンパイル)→段1.5(peripheral 1メソッドでスレッド境界を実機確認)へ進む。

## decisionsForYui (ゆいくんが決める論点)
1. ブロック名 / アイテム名(英: 'Ars CC Turret' で確定でよいか、日本語表示名をどうするか)。mod_id=arsccturret, レジストリ名=cc_turret で進める前提
2. 弾速 projectileSpeed のデフォルト値。design.md は config.speed と tile 既定をどちらも 1.5 blocks/tick で揃えた。これでよいか(0.75=AN標準寄り に下げる選択もある)
3. 初期ターゲットの既定フィルタ。design.md は『非プレイヤー生存(対Mob)』を既定にした。CIWS=対空なので飛ぶ敵(ファントム/ブレイズ等)を優先する別既定にするか
4. creative トグルの入口を peripheral setCreative() に一本化した(物理アイテム右クリックは廃止)。これでよいか。それとも survival 運用が主で creative 口は不要か
5. redstone 発射経路を初版で完全封鎖(Block#tick/neighborChanged を空 override)する方針で確定した。将来 redstone を副入力として残す余地を持つか、完全に CC 専用にするか
6. 収束ゲート aimTolDeg の既定 2.0度 と 連射 fireCooldownTicks=5(0.25秒) でよいか。対空CIWSとして連射をもっと詰めたいか(Java側 MIN_FIRE_INTERVAL=1tick まで上げられる)
7. GeckoLib 回転追従描画を初版は無回転最小にする(否定リスト §11)。砲身が標的を向いて回る見た目は段3命中実証後の追加層でよいか、それとも見た目も初版で欲しいか
