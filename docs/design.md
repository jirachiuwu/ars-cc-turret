# design.md — CC連携 自動照準・偏差射撃タレット (Ars Nouveau アドオン MOD)

> 一行で: Ars Nouveau の Rotating Spell Turret を継承し、CC:Tweaked から「手足」として操作できる対空タレットを作る。標的選択・偏差(リード)計算・追従発射の**頭脳は全部 Lua**。Java は列挙・照準・発射の口だけ開ける。弾速を peripheral フィールド化して Lua の偏差計算と実弾速を厳密一致させ、命中精度を担保する。

この設計書は3監査(技術破綻 / 思想逸脱 / 抜け)の指摘を、実ソース現物確認の上で全反映した最終版。引用コードは全て `D:/Claude/ars-cc-turret/refs/` のローカルソースで裏取り済み(行番号は実ファイル基準)。根拠が実機でしか確定しない箇所は **[実機検証]** と明記する。

---

## 0. 設計原則(SOLIS哲学の本案件への翻訳)

- **土台は軽く小さく**: 初版は Projectile 主軸の1発命中まで。Touch・自律モード・LoS・接近速度優先・二段リード・重力対応・GeckoLib回転描画は**§11「初版で作らないものリスト」に隔離**。最初から積まない。
- **器に徹する(委譲)**: 効果(Effect)・着弾VFX・トレイル色・寿命・衝突解決は Ars Nouveau 純正 `EntityProjectileSpell` + `EntitySpellResolver` に丸投げ。自前で持つのは「弾速を可変にする」一点だけ。
- **依存最小**: compile 依存は Ars Nouveau 本体 + GeckoLib(継承surfaceに露出) + CC:Tweaked API のみ。**Adam's Ars Plus には一切依存しない**(参考のみ)。CC API は `dan200.computercraft.api.*` の公開APIだけ触り、内部実装には触れない。
- **CC主役**: Java固定40tick連射を廃止。発射タイミング・標的判断は Lua が握る。**redstone 発射経路は初版で物理的に塞ぐ**(§6.1)。
- **参考元のバグを引き継がない**: Adam's `AutoSpellTurret`/`AutoTurretTile` には実ソース確認で複数の地雷がある(§9)。構造的に踏まない設計にする。

---

## 1. 全体像 — 二階建て(Java手足 / Lua頭脳)

```
┌─────────────────────────── CC:Tweaked Computer (Lua = 頭脳) ───────────────────────────┐
│  main.lua → turret.lua(状態機械) → targeting.lua(標的選択) / ballistics.lua(偏差解)   │
│                                                                                          │
│   毎tick:  ents = p.listEntities()        ← 範囲内の敵を uuid/type/位置/速度/距離で取得  │
│            target = select(ents, filter)  ← フィルタ・優先度・ロックは全部Lua述語        │
│            aimPt  = lead(muzzle,P,V,s)     ← 未来位置 = P + V*(dist/s) を反復で解く       │
│            p.aim(aimPt.x, aimPt.y, aimPt.z)← 小数座標へ照準指示                            │
│            if p.getAimError(...) <= tol then p.fire() end  ← 収束ゲートで発射             │
└──────────────────────────────────────┬───────────────────────────────────────────────┘
                                        │ peripheral 呼び出し(CC別スレッド → @LuaFunction(mainThread=true)でメインスレ同期)
┌──────────────────────────────────────┴───────────────────────────────────────────────┐
│  TurretPeripheral (IPeripheral)        ← @LuaFunction の薄い口。tileに委譲するだけ      │
│  CCTurretTile extends RotatingTurretTile  ← 弾速/NBT、aimVec、発射の正規ルート消化       │
│  CCTurret    extends RotatingSpellTurret  ← 自前 CC_BEHAVIOR_MAP + shootSpell override   │
│                                              + redstone経路(Block#tick/neighborChanged)封鎖│
│                                                                                          │
│  発射1発 → new EntityProjectileSpell(world, resolver) → addFreshEntity                   │
│            └─ 効果・VFX・色・寿命・衝突は AN純正が解決(器に徹する)。弾速だけ自前で渡す   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**役割分担の鉄則:**「事実を返す/指示を実行する」は Java。「いい/悪い・どれを撃つか・いつ撃つか」は Lua。

- Java が**しない**こと: 標的選択、偏差計算、発射周期の自動判断、種別判定、便利な合成述語(canFire等)。
- Java が**する**こと: 範囲内エンティティの事実列挙、小数座標→照準角の変換、発射の正規ルート実行(弾速可変)、Source枯渇/無限連射/redstone迂回の機械ガード。
- Lua が**する**こと: 上記以外の全頭脳。

---

## 1.5 tick駆動経路(この設計の生命線・最初に固定)

旋回収束・aimVec消化・発射消化は**全て tile の毎server tick に乗る**。その駆動経路を実ソースで固定する(`BasicSpellTurretTile implements ITickable`・実ファイルL26 確認):

- `CCTurret` は `RotatingSpellTurret → BasicSpellTurret → TickableModBlock(implements ITickableBlock)` を継承し、`getTicker()` を**継承で得る**。これが毎 server tick に `ITickable.tick()`(=**無引数 `tick()`**)を呼ぶ。
- `CCTurretTile.tick()` は**無引数 `tick()` を override**し、**必ず冒頭で `super.tick()` を呼ぶ**(親 `RotatingTurretTile.tick()` の server側回転補間 L74-91 をそのまま効かせる)。
- **絶対にやってはいけない**: 3引数 `tick(Level, BlockState, BlockPos)` を override すること。ITickable の警告どおり、これを super 呼びなしで生やすと無引数 `tick()` が呼ばれなくなり、**旋回収束・aimVec消化・発射消化が全て静かに死ぬ**。
- `BlockEntityType` は `CC_TURRET_TILE` 自身で構築するので `createTickerHelper` の `type2==type1` を満たす(§7.1)。

> なぜ参考元 Adam's `AutoTurretTile.tick()` は `super.tick()` を呼ばないのか: Adam's は親フィールドを再宣言(field shadowing, 実L58-63)し回転ロジックを丸ごと再実装したから。本MODは**再宣言しないので親 tick がそのまま効き、super を呼ぶのが正解**。実装時に参考元を見て super 呼びを消す逆行をするな(§9.1)。

---

## 2. Java peripheral API 仕様(手足の口・全署名)

**型名は `"ars_cc_turret"`**(`getType()` の戻り値。Lua `peripheral.wrap` 名はサーバが付ける `ars_cc_turret_N`)。

### 2.1 スレッドモデルの確定(監査critical反映・最重要)

CC の `@LuaFunction` は**デフォルトでコンピュータ別スレッド実行**(`LuaFunction.mainThread() default false`)。サーバのワールド/エンティティを別スレッドで直接触ると `ConcurrentModificationException` でクラッシュする。**自前 executeBlocking + volatile 退避機構は発明しない。CC公式の正解 `@LuaFunction(mainThread=true)` を使う。**

| 区分 | 対象メソッド | スレッド指定 |
|---|---|---|
| ワールド走査を伴う read | `listEntities` / `getMuzzle` / `getAimDir` / `getAimError` / `getSource` / `getSpellCost` / `isLoaded` | **`@LuaFunction(mainThread = true)`**(CCが自動でサーバメインスレッド同期+結果待ちをやる) |
| ワールドに触る write | `aim` / `fire` / `setProjectileSpeed` / `setCreative` | **`@LuaFunction(mainThread = true)`**(メインスレで直接適用。volatile/退避フラグ不要) |
| 純フィールド read | `getProjectileSpeed` / `getCreative` | `@LuaFunction`(mainThread不要。フィールド読みだけ) |

> `mainThread=true` を付けた瞬間、tile のメソッドは server tick と同じスレッドで走るので、`aimVec` も `shootSpell` も**直接呼んでよい**(別スレ退避が不要になり構造が単純化)。発射の「1tick1発」化は tick 側でなく `fire()` 内の `lastFireTick` ガードで担保する(§7.2)。**[実機検証]**: `mainThread=true` でブロッキング戻り値が正しく Lua に返るか、2台同時アクセスでクラッシュしないか(段1.5)。

### 2.2 単位の一元定義(混乱防止・最重要)

| 量 | 単位 | 根拠 |
|---|---|---|
| 座標 (x,y,z) | **ワールド絶対座標(小数可)** | Lua が距離・偏差を自由計算するため相対化しない |
| 速度 (vx,vy,vz) | **ブロック/tick** (`entity.getDeltaMovement()`) | 弾速と同一単位に揃え `t=dist/s` を成立させる |
| 弾速 s | **ブロック/tick** | `EntityProjectileSpell.shoot` の velocity 引数と物理的に同一(§6.2) |
| 距離 | ブロック(ユークリッド) | — |
| 照準角 | **度(degree)** | tile 内部 `rotationX/Y` が度保持(`getShootAngle` で度→rad変換) |

> tick=秒の取り違えが唯一の現実的な精度バグ要因。s は [blocks/tick] であり [blocks/sec] ではない。20倍ズレたら真っ先にここを疑う(§8 段3)。

### 2.3 read系

| メソッド | スレッド | 戻り値 | 内容 |
|---|---|---|---|
| `listEntities([range])` | main | `{ [1]={uuid,type,x,y,z,vx,vy,vz,distance,isAlive,isPlayer}, … }` | range 既定30。範囲内 `LivingEntity` を1始まりIntキーtableで列挙(`ipairs`可) |
| `getMuzzle()` | main | `{x,y,z}` | 発射点 = `getDispensePosition`(ブロック中心 + 0.5·照準ベクトル)。偏差の砲口 T |
| `getAimDir()` | main | `{x,y,z}` | 現照準の正規化ベクトル = `getShootAngle().normalize()` |
| `getAimError(dx,dy,dz)` | main | `number`(度) | 目標方向(正規化前可)と現照準の角度差。Java側で `acos(dot)`。収束ゲート用 |
| `getProjectileSpeed()` | (なし) | `number` | 弾速 s [blocks/tick]。純フィールド読み |
| `getSource()` | main | `number` | **単一プロバイダが供給できる最大量** = `max over providers`(§下注)。合算しない |
| `getSpellCost()` | main | `number` | 装填スペル1発のコスト(`tile.getManaCost()`)。未装填は 0。creative時 0 |
| `isLoaded()` | main | `boolean` | 装填スペル有無 |
| `getCreative()` | (なし) | `boolean` | creativeフラグ |

> **`getSource()` セマンティクス修正(監査high反映)**: `SourceUtil.takeSource` は providers を回し**単一プロバイダが必要量を単独充足する場合のみ**成功し、その1基から引く(複数ジャーをプールして合算しない)。よって `getSource()` は「全ジャー合計」ではなく**「最大単一プロバイダ供給量」**を返す。これで Lua の発射可否判断(`getSource() >= getSpellCost()`)が実消費(`takeSourceWithParticles`)と一致し、空撃ち無限ループを防ぐ。実装は `SourceUtil` の供給判定APIを各 provider で評価し最大値を取る([実機検証]: AN 4.12.7 の `SourceUtil`/`ISpecialSourceProvider` の正確な判定API名を実 jar で確認。無ければ `takeSource` のドライラン相当を自前で1基ずつ評価)。
>
> **`canFire()` は初版から削除**(監査low反映): `isLoaded && (creative || getSource()>=getSpellCost())` は Lua が素の事実から組める合成述語。Java に置くと知能漏れ。Lua側 config で組む。

### 2.4 write系

| メソッド | スレッド | 戻り値 | 内容 |
|---|---|---|---|
| `aim(x,y,z)` | main | `void` | ワールド絶対座標へ照準(`aimVec`)。`neededRotationX/Y` を設定。**`updateBlock()` は呼ばず `setChanged()` のみ**(§6.3) |
| `fire()` | main | `boolean` | 1発発射要求 → その場で `shootSpell` 正規ルート実行。成功true / (未装填・Source枯渇・連射ガード)false |
| `setProjectileSpeed(s)` | main | `void` | 弾速設定(`max(0.05, min(2.5, s))`)。NBT永続 |
| `setCreative(on)` | main | `void` | creativeフラグ(NBT永続)。Source無料化(`getManaCost`が0返し) |

> **`autonomous` 一式は初版署名から削除**(監査low反映): 「Javaで何もしないフラグ」を予約APIとして積むのは「準備の準備をするな」に触れる。Lua が全制御するので Java保持不要。必要になってから足す。

### 2.5 IPeripheral 実装スケッチ(mainThread署名で全面修正)

```java
public class TurretPeripheral implements IPeripheral {
    private final CCTurretTile tile;
    public TurretPeripheral(CCTurretTile t){ this.tile = t; }

    @Override public String getType(){ return "ars_cc_turret"; }
    @Override public boolean equals(@Nullable IPeripheral o){
        return o instanceof TurretPeripheral p && p.tile == this.tile; }  // 同一tile == で同一視
    @Override public Object getTarget(){ return tile; }

    // --- world走査read: mainThread=true(CCがメインスレ同期+結果待ち) ---
    @LuaFunction(mainThread = true) public final Map<Integer,Map<String,Object>> listEntities(Optional<Double> range){
        return tile.luaListEntities(range.orElse(30.0)); }
    @LuaFunction(mainThread = true) public final Map<String,Double> getMuzzle(){ return tile.luaMuzzle(); }
    @LuaFunction(mainThread = true) public final Map<String,Double> getAimDir(){ return tile.luaAimDir(); }
    @LuaFunction(mainThread = true) public final double getAimError(double dx,double dy,double dz){ return tile.luaAimError(dx,dy,dz); }
    @LuaFunction(mainThread = true) public final double getSource(){ return tile.luaMaxSingleSource(); }
    @LuaFunction(mainThread = true) public final int getSpellCost(){ return tile.getManaCost(); }
    @LuaFunction(mainThread = true) public final boolean isLoaded(){ return !tile.getSpellCaster().getSpell().isEmpty(); }

    // --- 純フィールドread: mainThread不要 ---
    @LuaFunction public final double  getProjectileSpeed(){ return tile.getProjectileSpeed(); }
    @LuaFunction public final boolean getCreative(){ return tile.getCreative(); }

    // --- write: mainThread=true(メインスレで直接適用。volatile/退避不要) ---
    @LuaFunction(mainThread = true) public final void    aim(double x,double y,double z){ tile.aimVec(new Vec3(x,y,z)); }
    @LuaFunction(mainThread = true) public final boolean fire(){ return tile.requestFire(); }
    @LuaFunction(mainThread = true) public final void    setProjectileSpeed(double s){ tile.setProjectileSpeed(s); }
    @LuaFunction(mainThread = true) public final void    setCreative(boolean on){ tile.setCreative(on); }
}
```

> 注: `@LuaFunction` は `public final` 必須。`Map<Integer,...>` は Lua table(配列)に自動変換。**[実機検証]**: CC 1.116.1 で Integer1始まりキーが Lua 配列(`ipairs`可)になるか、最小 `getTest()->Map.of(1,"a",2,"b")` で確認。

---

## 3. Lua頭脳 — 偏差(リード)/標的選択/追従ループ

### 3.1 弾道モデル(最重要・実ソース確定)

**一次(等速直線)で確定。重力・空気抵抗の数値解は不要。** 根拠(Ars実ソース確認):

- `EntityProjectileSpell.isNoGravity = true`(デフォルト)。
- `tickNextPosition()` は重力OFF時 deltaMovement を一切変更しない → 毎tick等速で直進。
- `shoot(x,y,z,velocity,inaccuracy)` は `normalize(dir).scale(velocity)` → `setDeltaMovement`。**inaccuracy=0 なら deltaMovement = normalize(dir)·velocity** が厳密成立。

よって**実弾速[blocks/tick] = velocity引数 = peripheral の projectileSpeed フィールド**。Lua の `t = distance / s` がそのまま物理と一致する。これが偏差精度の核。

### 3.2 偏差の反復解 (`ballistics.lua`, 純関数・ゲーム不要でテスト可)

砲口 T、標的位置 P、標的速度 V、弾速 s(全て blocks/tick)。固定点反復で命中 t を解く。

```lua
local M = {}
local function sub(a,b) return {x=a.x-b.x,y=a.y-b.y,z=a.z-b.z} end
local function add(a,b) return {x=a.x+b.x,y=a.y+b.y,z=a.z+b.z} end
local function scale(a,k) return {x=a.x*k,y=a.y*k,z=a.z*k} end
local function len(a) return math.sqrt(a.x*a.x+a.y*a.y+a.z*a.z) end

-- 戻り: aimPoint(未来位置), t  /  解なしは nil
function M.lead(T, P, V, s, opts)
  opts = opts or {}
  local t = len(sub(P, T)) / s              -- 初期推定(標的静止扱い)
  for _ = 1, (opts.maxIter or 6) do
    local future = add(P, scale(V, t))
    local tNew = len(sub(future, T)) / s
    if math.abs(tNew - t) < (opts.eps or 0.01) then t = tNew; break end
    t = tNew
  end
  local future = add(P, scale(V, t))
  if t ~= t or t > (opts.maxT or 200) then return nil, t end  -- NaN/射程外ガード
  return future, t
end

-- 視線方向に弾速以上で逃げる標的を先に弾く(安い早期判定)
function M.escapes(T, P, V, s)
  local d = sub(P, T); local dl = len(d)
  if dl < 1e-6 then return false end
  return (V.x*d.x + V.y*d.y + V.z*d.z) / dl >= s
end
return M
```

収束特性: `|V| < s` なら2〜4回で eps 以下。視線方向に s 近くで逃げると t が伸びるので `escapes()`/`maxT` で打ち切る。

### 3.3 標的選択 (`targeting.lua`) — 初版は nearest固定

設計方針8(敵/味方/プレイヤー/任意を Lua述語で柔軟指定)は Java が事実列挙だけ返すことで満たす。Adam's の mode 0/1/2 3固定は採用しない。

**初版の prio は `nearest` 固定 + 生存フィルタのみ**(監査low反映)。接近速度優先(`fastestClose`)・ロックチャタリング防止・LoS は**§11「初版で作らないもの」へ隔離**。

```lua
local M = {}
M.priorities = {
  nearest = function(a,b) return a.dist < b.dist end,
}
function M.select(ents, T, filter, prioLess, lockUuid)
  local cands = {}
  for _,e in ipairs(ents) do
    if e.isAlive and filter(e) then e.dist = e.distance; cands[#cands+1]=e end
  end
  if #cands == 0 then return nil end
  if lockUuid then for _,e in ipairs(cands) do if e.uuid==lockUuid then return e end end end
  table.sort(cands, prioLess)
  return cands[1]
end
return M
```

**LoS(視線遮蔽)**: Adam's の `checkLineOfSight` は整数刻みサンプルで精度が低い(実L251-269: `(int)(i*diffX/distance)` で間引く近似)。**流用しない。** 初版は撃って外れたら次標的にフォールバック(無限ループは cooldown で防ぐ)。精度が要れば Java側 `hasLineOfSight` を `level.clip` 1回で正確に足す(§11)。

### 3.4 追従ループ (`turret.lua`) — 状態機械

```lua
local P = peripheral.wrap(config.name)
P.setProjectileSpeed(config.speed)     -- 偏差で使う弾速と実弾速を一致させる(命中の前提)
local lock, cooldown = nil, 0

while true do
  local T    = P.getMuzzle()
  local ents = P.listEntities(config.range)
  local tgt  = targeting.select(ents, T, config.filter, config.prio, lock)

  if not tgt then
    lock = nil                          -- 標的ロスト: 照準維持(再捕捉が速い)
  else
    lock = tgt.uuid
    local Pp = {x=tgt.x, y=tgt.y, z=tgt.z}
    local V  = {x=tgt.vx, y=tgt.vy, z=tgt.vz}
    local s  = P.getProjectileSpeed()   -- ★必ずJavaのクランプ後の真値を読む(config.speed直読み禁止)
    local aimPt = (not ballistics.escapes(T,Pp,V,s)) and ballistics.lead(T,Pp,V,s,config.lead) or Pp
    if aimPt then                        -- ★aimPt==nil(射程外/解なし)なら撃たない
      P.aim(aimPt.x, aimPt.y, aimPt.z)   -- 毎ループ最新解で照準更新し続ける(固定して待たない)
      local err = P.getAimError(aimPt.x-T.x, aimPt.y-T.y, aimPt.z-T.z)
      local cost = P.getSpellCost()
      local ok   = P.isLoaded() and (P.getCreative() or P.getSource() >= cost)  -- canFireをLuaで合成
      if err <= config.aimTolDeg and cooldown <= 0 and ok then
        if P.fire() then cooldown = config.fireCooldownTicks end
      end
    end
    -- aimPt==nil のときは fire しない(明示)。標的射程外/逃走中の挙動を閉じる。
  end
  if cooldown > 0 then cooldown = cooldown - 1 end
  os.sleep(0.05)                         -- 約20Hz(server tick同期)
end
```

**弾速の真値ルール(監査medium反映)**: 偏差で使う `s` は**常に `P.getProjectileSpeed()` の戻り(=Javaがクランプした真値)**。`config.speed` は `setProjectileSpeed` への入力にのみ使う。`config.speed` を偏差に直読みすると、クランプ境界(例 3.0→2.5)で Lua想定値と実弾速が食い違う。

**aim/fire ズレの解消**: 「一度 aim→待つ→撃つ」を**やらない**。毎ループ aim を最新偏差解で更新し続け、誤差が閾値に入った**その時点の最新aim**で fire する。

**旋回遅延の織り込み**: 旋回は server tick で `diff*0.1f`(指数収束、`|diff|<0.1°` でスナップ・実L74-91)。固定待ちは外す。**誤差ベースの収束ゲート**(`getAimError ≤ aimTolDeg`)で撃つ。二段リードは§11。

### 3.5 config.lua

```lua
return {
  name = "ars_cc_turret_0",
  range = 30,
  speed = 1.5,                 -- blocks/tick。setProjectileSpeed への入力。偏差はP.getProjectileSpeed()を読む
  aimTolDeg = 2.0,             -- 収束ゲート[度]
  fireCooldownTicks = 5,       -- 連射間隔
  lead = { maxIter = 6, eps = 0.01, maxT = 200 },
  filter = function(e) return not e.isPlayer and e.isAlive end,  -- 既定:非プレイヤー生存
  prio = require("targeting").priorities.nearest,
}
```

> **既定値の一致(監査medium反映)**: `config.speed=1.5` と CCTurretTile の `projectileSpeed` 既定をどちらも実用域で揃える。起動 `setProjectileSpeed(config.speed)` 後は必ず `getProjectileSpeed()` を読む(turret.lua の `s=P.getProjectileSpeed()` で担保済)。

### 3.6 Lua偏差の最小検証(本実装前・ゲーム不要)

`ballistics.lua` 単体を素のLua/craftos-pcで回し、既知 (T,P,V,s) で命中をシミュレート:

```
for each (P,V,s):
  aim,t = lead(T,P,V,s)
  bullet = T + normalize(aim-T) * s * t
  target = P + V*t
  assert(len(bullet-target) < 0.5)   -- 0.5block以内で命中
-- クランプ境界ケースを追加(監査medium): s=0.04→0.05, s=3.0→2.5 を setProjectileSpeed相当で丸めてから lead に渡し一致確認
```

通れば偏差の核は固い。Java不要・ゲーム起動不要で即回る。

---

## 4. 依存ビルド / 継承(build.gradle 具体)

### 4.1 土台と核心リスク

土台 `D:/Claude/ars-no-iframes`(FG `[6.0,6.2)`, official mappings 1.20.1, JDK17, Forge 47.2.0)を複製して `D:/Claude/ars-cc-turret/` で開発。`build.gradle`/`gradlew`/`gradle/wrapper`/`settings.gradle` を流用。

**一番危ない核心(ビルド)**: CurseForge配布の `ars_nouveau-…-all.jar` は **MC親クラス呼び出しが SRG名**。official mappings の dev 環境とは名前空間が一致せずリンクできない。ローカル jar を flatDir で直接 compile 依存にすると、本実装を数百行書いた後に大量の unresolved/NoSuchMethod ループに落ちる。

→ 回避策: **`fg.deobf()` でラップした CurseMaven 依存に限定**(SRG→official remap を FG に任せる唯一の手段)。

**現物確認: 土台 ars-no-iframes の `repositories {}` は完全に空**(実L42-43)。Ars への compile 依存を持たず Forge同梱だけで動いていた。よって fg.deobf でラップした Ars/CC/GeckoLib の**推移依存(SLF4J/commons/cobalt/netty 等)を解決する先が無い** → そのままでは段1ビルドが `Could not resolve` で落ちる(監査critical反映)。**`mavenCentral()` と Forge maven の明示追加が必須。**

### 4.2 build.gradle — repositories(置換・推移依存解決先を必ず含める)

```gradle
repositories {
    mavenCentral()                                                               // ★推移依存(SLF4J/commons/cobalt等)の解決先。必須
    maven { url 'https://maven.minecraftforge.net/' }                            // ★Forge maven。必須
    maven { url 'https://www.cursemaven.com';  content { includeGroup 'curse.maven' } }   // Ars Nouveau(deobf化して取込)
    maven { url 'https://squiddev.cc/maven/';  content { includeGroup 'cc.tweaked' } }     // CC:Tweaked
    maven { url 'https://dl.cloudsmith.io/public/geckolib3/geckolib/maven/' }              // GeckoLib(継承surfaceに露出)
    maven { url 'https://modmaven.dev' }                                         // 退避路: GeckoLib/CurseMaven 補完ミラー(cloudsmith落ち対策)
}
```

### 4.3 build.gradle — dependencies(置換)

```gradle
dependencies {
    minecraft "net.minecraftforge:forge:${mc_version}-${forge_version}"

    // Ars Nouveau 4.12.7(継承元・compile依存)。fg.deobf が SRG→official remap する。
    implementation fg.deobf("curse.maven:ars-nouveau-401955:6688854")  // projectId=401955, fileId=6688854=4.12.7-all

    // GeckoLib(継承元 BasicSpellTurretTile が GeoBlockEntity を implements する為 compile必須)
    implementation fg.deobf("software.bernie.geckolib:geckolib-forge-${mc_version}:${gecko_version}")

    // CC:Tweaked(peripheral実装)。core-apiは純Java(SRG非依存)ゆえ非deobf。forge-apiはMC参照含むのでdeobf。
    compileOnly         "cc.tweaked:cc-tweaked-${mc_version}-core-api:${cct_version}"
    compileOnly fg.deobf("cc.tweaked:cc-tweaked-${mc_version}-forge-api:${cct_version}")
    runtimeOnly fg.deobf("cc.tweaked:cc-tweaked-${mc_version}-forge:${cct_version}")
}
```

> `curse.maven:ars-nouveau-401955:6688854` の fileId は配布実体と[実機検証]で突合。解決失敗時は modmaven.dev / CurseMaven の geckolib を退避路に持つ。

### 4.4 gradle.properties — 追記

```properties
# mc_version=1.20.1 / forge_version=47.2.0 は土台のまま流用
mod_id=arsccturret
mod_name=Ars CC Turret
package_group=com.yui.arsccturret
gecko_version=4.4.4
cct_version=1.116.1
```

> AN 4.12.7 は forge `[47.1.0,)` 要求 → 47.2.0 で満たす。bytecode 不整合(NoSuchMethod)が出たら 47.1.x へ下げる退避路(AN要求の下限 47.1.0)。

### 4.5 継承の技術的実現性(AT不要・実証済み)

`RotatingSpellTurret` / `RotatingTurretTile` を**そのまま継承可能。Access Transformer 不要。** 根拠: 両クラスは public、継承で使う全メンバが public(実ソース確認: tile側 `rotationX/Y`/`neededRotationX/Y` public フィールド L27-30、`aim`/`getShootAngle`/`getRotationX/Y`/`setRotationX/Y`/`tick`、block側 `shootSpell`/`getDispensePosition`/`orderedByNearest`/`newBlockEntity`)。Adam's が別パッケージから実際に継承・super呼び出ししている実例が動いている。

**継承で「タダで」得られるもの**(実ソース確認):
- server側旋回補間: `RotatingTurretTile.tick()` L74-91 が `rotationX/Y` を `neededRotationX/Y` へ `diff*0.1f` ずつ寄せ、`|diff|<0.1` でスナップ。継承+super.tick()で照準収束が動く。
- スペル装填: `BasicSpellTurretTile.spellCaster`(TurretSpellCaster)+ `getManaCost()` + NBT serialize/load(L44-58)。
- GeckoLib recoil アニメ駆動(`registerControllers`/`startAnimation` で `playRecoil` → "recoil" クリップ再生・実L67-94)、`getShootAngle()`。

> `getShootAngle()` はAN原文コメントで "Don't ask me why it works, it was pure luck."(実L169)。**これを「修正」しない。** 既存 `getDispensePosition`/`orderedByNearest` と整合した一式なので器に徹してそのまま使う。

### 4.6 推移依存

CurseMaven は推移依存を解決しない(§4.1で `mavenCentral()`/Forge maven を入れる理由)。継承元 `BasicSpellTurretTile implements GeoBlockEntity`(実L26)で型に `software.bernie.geckolib.*` が露出するため、**GeckoLib 4.4.4 を compile classpath に明示追加が必須**。Patchouli/Curios/JEI は AN本のdepだが自継承surfaceには現れないので compileJava には不要(実ゲーム完全起動時のみ runtimeOnly が要る場合あり → [実機検証] で `runClient` 時に判断)。

### 4.7 ビルド検証(機械で白黒・最初にやる)

```
& 'D:\Claude\ars-cc-turret\gradlew.bat' --no-daemon --refresh-dependencies compileJava
```
- `BUILD SUCCESSFUL` かつ `.class` 生成 = 依存解決+継承+remap が全通り → 本実装へ進んでよい。

失敗診断表(監査反映: repositories 不足も明記):
| エラー | 原因 | 対処 |
|---|---|---|
| `Could not resolve org.slf4j…` / `…commons…` / `…cobalt…` | **推移依存の解決先不足** | `repositories` に `mavenCentral()`/Forge maven があるか確認(§4.2) |
| `package com.hollingsworth.arsnouveau… does not exist` | AN依存未解決 | CurseMaven 座標/URLミス確認 |
| `cannot find symbol: method m_xxxxx_` | fg.deobf 未適用(remap失敗) | `--refresh-dependencies` 再実行 / `~/.gradle/caches/forge_gradle/deobf` 削除 |
| `package software.bernie.geckolib does not exist` | GeckoLib repo 解決失敗 | repo URL を modmaven.dev 退避路へ切替 |

---

## 5. Form 自前 BEHAVIOR_MAP と 効果/VFX 委譲

### 5.1 Form制限を超える根拠(実ソース確定)

`BasicSpellTurret.shootSpell` は `resolver.castType != null && MAP.containsKey(castType)` だけで撃てる Form を決める(実L126)。`RotatingSpellTurret` は自前 `ROT_TURRET_BEHAVIOR_MAP` を持ち shootSpell を override してそちらを見せている(実L53-70)。**= BEHAVIOR_MAP は「撃てる Form の許可リスト」そのもの。**

→ `CCTurret extends RotatingSpellTurret` で自前 static `CC_BEHAVIOR_MAP` を宣言し、`shootSpell` を override してそれを参照させる。

- 登録: `MethodProjectile.INSTANCE`(弾速可変・主軸)。Touch は§11(初版は Projectile のみで1発命中)。
- 登録しない Form(Self/Orbit/AOE等)= 意図的非対応。`use()` が `containsKey` で拒否し alert(本体機構そのまま)。

### 5.2 効果/VFXが「タダで乗る」根拠(実ソース確定)

自前 onCast は本体と同じく `new EntityProjectileSpell(world, resolver)` → `addFreshEntity` するだけ(本体 L81-92 / Rotating L154-161)。Effect解決・着弾VFX・トレイル色・寿命・衝突は一切自前実装しない。ctor `(Level, SpellResolver)` が resolver を保持し色を同期、`tick()` が衝突→resolver で Effect を解決。

→ **発射ルート(resolver/ctor)を正しく踏めば効果もVFXも自動で乗る。** 引数を本体と1対1一致させるのが肝。

### 5.3 自前 CC_BEHAVIOR_MAP + shootSpell override(redstone封鎖込み)

```java
public class CCTurret extends RotatingSpellTurret {
  public static final HashMap<AbstractCastMethod, ITurretBehavior> CC_BEHAVIOR_MAP = new HashMap<>();
  static {
    CC_BEHAVIOR_MAP.put(MethodProjectile.INSTANCE, (resolver, world, pos, fakePlayer, ipos, dir) -> {
      if (!(world.getBlockEntity(pos) instanceof CCTurretTile tile)) return;
      EntityProjectileSpell spell = new EntityProjectileSpell(world, resolver); // ← 効果/色/VFX はここで乗る
      spell.setOwner(fakePlayer);
      spell.setPos(ipos.x(), ipos.y(), ipos.z());
      Vec3 v = tile.getShootAngle().normalize();          // 継承した照準ベクトル(pure luck式)
      float velocity = (float) tile.getProjectileSpeed(); // ★ AN標準式を捨てフィールド値=Lua可変
      spell.shoot(v.x(), v.y(), v.z(), velocity, 0);      // inaccuracy=0 必須(velocity厳密化)
      world.addFreshEntity(spell);                        // 以降 tick() が衝突→resolver で効果解決
    });
    // MethodTouch は §11(初版後追い)
  }

  // ★ redstone発射経路の封鎖(監査critical/high反映) ---
  // 親 BasicSpellTurret.tick(BlockState,ServerLevel,BlockPos,RandomSource) は無条件に shootSpell を直叩きする(実L71-74)。
  // これは neighborChanged→scheduleTick 由来の「Block#tick」で、tile の発射ゲートを迂回する。CC完全主役を成立させるため両方塞ぐ。
  @Override public void tick(BlockState s, ServerLevel w, BlockPos p, RandomSource r){ /* 何もしない: redstone発射を無効化 */ }
  @Override public void neighborChanged(BlockState s, Level w, BlockPos p, Block b, BlockPos from, boolean moving){
    /* scheduleTick を張らない: redstoneトリガを無効化。waterlogged等の必要処理があれば最小限のみ呼ぶ */ }

  @Override
  public void shootSpell(ServerLevel world, BlockPos pos) {
    if (!(world.getBlockEntity(pos) instanceof CCTurretTile tile)) return;
    ISpellCaster caster = tile.getSpellCaster();
    if (caster.getSpell().isEmpty()) return;
    int manaCost = tile.getManaCost();                                          // creative時 tile が0返す
    if (manaCost > 0 && SourceUtil.takeSourceWithParticles(pos, world, 10, manaCost) == null) return;
    Networking.sendToNearby(world, pos, new PacketOneShotAnimation(pos));        // recoilアニメ
    Position ipos = getDispensePosition(new BlockSourceImpl(world, pos), tile);  // 継承(Rotating版・実L75)
    FakePlayer fake = ANFakePlayer.getPlayer(world);
    fake.setPos(pos.getX(), pos.getY(), pos.getZ());
    EntitySpellResolver resolver = new EntitySpellResolver(
        new SpellContext(world, caster.getSpell(), fake, new TileCaster(tile, SpellContext.CasterType.TURRET)));
    if (resolver.castType != null && CC_BEHAVIOR_MAP.containsKey(resolver.castType)) {
      CC_BEHAVIOR_MAP.get(resolver.castType)
          .onCast(resolver, world, pos, fake, ipos, orderedByNearest(tile)[0].getOpposite());  // 引数を本体と1対1一致
      caster.playSound(pos, world, null, caster.getCurrentSound(), SoundSource.BLOCKS);
    }
  }

  @Override public BlockEntity newBlockEntity(BlockPos pos, BlockState state){ return new CCTurretTile(pos, state); }
  // ★ setPlacedBy / getShootAngle 系は override しない(親の正しい実装を継承。§9.1の罠回避)
}
```

> `ITurretBehavior` の `onCast(...)` は **default メソッド**なので、このインターフェースは functional interface ではない。**ラムダ不可。`new ITurretBehavior(){ @Override public void onCast(...){...} }` の匿名クラスで実装する**(段1bでコンパイルエラー `機能インターフェースではありません` を踏んだ。import に `net.minecraft.core.Direction` と `net.minecraft.world.entity.player.Player` が必要)。`SpellContext`/`EntitySpellResolver`/`TileCaster`/`CasterType.TURRET`/`orderedByNearest(tile)[0].getOpposite()` は本体 `RotatingSpellTurret.shootSpell`(実L62-68)と**1対1一致**(差分を作らないことが効果不乗回避の肝)。

---

## 6. 連射 / 弾速 / 照準 / 既知課題対応

### 6.1 連射 + redstone封鎖(Java固定40tick撤廃 → CC fire()駆動)

Adam's の `ticksPerSignal=40` カウンタ機構(実L53,177-181)+ redstone駆動(`getBlockState().tick(...)` 実L179)を**採用しない**。発射は `peripheral.fire()` が**その server tick で正規ルートを1回実行**する。

**redstone迂回の封鎖(監査critical/high反映)**: 参考元 `BasicSpellTurret` には2系統の tick がある。(a) BlockEntity の無引数 `tick()`(§1.5)、(b) Block の `tick(BlockState,ServerLevel,BlockPos,RandomSource)`(実L71-74)で、後者は redstone scheduleTick から呼ばれ `shootSpell` を無条件直叩きする。**oneShotRequested 的なゲートは (a) にしか効かず (b) を迂回する。** よって `CCTurret` で **(b) と `neighborChanged` を override して空に**し、redstone 発射を物理的に塞ぐ(§5.3)。これで「CC完全主役」が初版から成立する。

Java側ガードは3つだけ(`fire()` 内):
- (a) **1tick1発上限**: `lastFireTick` ガード(`MIN_FIRE_INTERVAL=1tick`)。
- (b) **Source枯渇**: `manaCost>0 && takeSourceWithParticles==null` で false(creative時 cost=0素通り)。
- (c) **未装填**: `caster.getSpell().isEmpty()` で false。

### 6.2 弾速(Lua可変・Augment問題の根本回避)

本体/Rotating の標準式 `velocity = max(0.1, 0.75 + acc/2)`(実 Basic L85 / Rot L159)、Adam's の `0.5F` 固定(実L229)を**全て捨てる**。自前 onCast で `tile.getProjectileSpeed()`(NBT永続・peripheral可変)を直接 velocity に渡す。

- 飛翔速度Augmentは天井が低く可変不能 → バイパスして根本回避。
- 偏差計算で使う弾速 = Java実弾速 = 同一フィールド由来 → **偏差精度が定義上一致**。
- **トンネリング注意**: `setProjectileSpeed` で上限クランプ(0.05〜10.0、2026-06-06 拡張)。`EntityProjectileSpell.tick` はレイキャスト衝突するので通常緩和されるが、極端高速(>~3 blocks/tick)で抜ける可能性。安全上限は[実機検証]継続中。
- **自爆注意**: 弾は砲口=ブロック中心+0.5·照準ベクトルからスポーン。高弾速かつ近接で自タレット/隣接ブロックへ即着弾する境界がある。理論上、スポーン点が中心+0.5なので隣接ブロックに対しては1tick目の移動で `s` ブロック進む → `s>~0.5` でブロック際を越える。**[実機検証]**: 近接・高弾速での自爆条件。

### 6.3 照準(整数→小数 aim・updateBlock封印で同期間引き)

`RotatingTurretTile.aim(BlockPos, Player)` は整数ブロック中心しか狙えず Player依存処理(`ParticleUtil.beam`/`PortUtil`)を含む(実L94-121)。偏差は小数未来位置を狙うので Vec3 受けの `aimVec(Vec3)` を新設。角度逆算式は既存 `aim` と**同一**(実L97-117)で `getShootAngle` と整合させる。Player依存処理は除去(CC無人運用)。

**`updateBlock()` を毎tick呼ばない(監査high反映)**: `ModdedTile.updateBlock()` は `sendBlockUpdated(...,3)` =フルブロック更新パケット。Lua は毎ループ(約20Hz)aim を叩くので、毎回 `updateBlock` するとタレット1台あたり毎tick全近傍プレイヤーへ同期パケットが飛び、CIWS編成でスパムになる。**`aimVec` は `neededRotationX/Y` をセットして `setChanged()` のみ**にし、クライアント描画同期は `RotatingTurretTile` の既存 `getUpdateTag`/`onDataPacket` 経路 + バニラの低頻度同期に委ねる(バニラ `RotatingTurretTile.tick` も回転変化時は `setChanged()` のみ・実L81,90)。

### 6.4 既知課題 → 対応 表

| 課題(参考元で発覚) | 真因(実ソース) | 本設計の対応 |
|---|---|---|
| Form制限(Projectile/Touchのみ) | shootSpell が static map の containsKey 判定(Basic L126) | 自前 CC_BEHAVIOR_MAP + shootSpell override。Projectile登録、他は意図的非対応 |
| Augment velocity 不反映/天井低 | `0.75+acc/2`(Basic L85, Rot L159)/`0.5F`固定(Adams L229) | velocity = `tile.getProjectileSpeed()`(Lua可変) |
| 偏差精度ズレ | 計算弾速とJava実弾速が別物 | shoot の velocity引数=blocks/tick=同一フィールド。isNoGravity=true 等速直進で `t=dist/s` 厳密 |
| 効果が乗らない疑惑 | 正規 resolver ルート逸脱の疑い | 正規最小ルートのみ。引数を本体と1対1一致 |
| 連射40tick固定 + redstone迂回 | `ticksPerSignal=40`(Auto L53) / Block#tick 直叩き(Basic L72) | カウンタ廃止。`fire()`で1発消化 + Block#tick/neighborChanged を空 override |
| 整数照準のみ | `aim(BlockPos)`(Rot L94) | `aimVec(Vec3)` 追加。`updateBlock`封印・`setChanged`のみ |

---

## 7. レジストリ / NBT

### 7.1 レジストリ登録(自前 DeferredRegister・Forge標準)

本体 AN は private な `RegistryWrapper`+ヘルパを使うので自MODでは使えない。標準 `DeferredRegister` で再現。

```java
public class CCRegistry {
  public static final String MODID = "arsccturret";
  public static final DeferredRegister<Block> BLOCKS = DeferredRegister.create(ForgeRegistries.BLOCKS, MODID);
  public static final DeferredRegister<Item> ITEMS = DeferredRegister.create(ForgeRegistries.ITEMS, MODID);
  public static final DeferredRegister<BlockEntityType<?>> TILES = DeferredRegister.create(ForgeRegistries.BLOCK_ENTITY_TYPES, MODID);

  public static final RegistryObject<CCTurret> CC_TURRET = BLOCKS.register("cc_turret",
      () -> new CCTurret(BlockBehaviour.Properties.of().strength(2.3f).noOcclusion().requiresCorrectToolForDrops()));
  public static final RegistryObject<BlockItem> CC_TURRET_ITEM = ITEMS.register("cc_turret",
      () -> new BlockItem(CC_TURRET.get(), new Item.Properties()));
  public static final RegistryObject<BlockEntityType<CCTurretTile>> CC_TURRET_TILE = TILES.register("cc_turret",
      () -> BlockEntityType.Builder.of(CCTurretTile::new, CC_TURRET.get()).build(null));

  public static void init(IEventBus bus){ BLOCKS.register(bus); ITEMS.register(bus); TILES.register(bus); }
}
```

> **tick駆動の保証(§1.5)**: `CC_TURRET_TILE` 自身を BE-type に使うので `createTickerHelper` の `type2==type1` が成立し、継承した `getTicker()` が無引数 `tick()` を毎 server tick に呼ぶ。`CCTurretTile` は `super(CCRegistry.CC_TURRET_TILE.get(), pos, state)` を呼ぶ(`RotatingTurretTile` の `(BlockEntityType<?>,BlockPos,BlockState)` public ctor・実L19)。

### 7.2 CCTurretTile 中核(NBT + 弾速 + 発射消化 + aimVec + Lua read)

```java
public class CCTurretTile extends RotatingTurretTile {
  private double projectileSpeed = 1.5;         // blocks/tick(config.speed既定と一致). NBT永続. Lua可変
  private boolean creative = false;             // NBT永続
  private static final double SPEED_MIN = 0.05, SPEED_MAX = 2.5;
  private long lastFireTick = Long.MIN_VALUE;
  private static final long MIN_FIRE_INTERVAL = 1;
  private TurretPeripheral peripheral;

  public CCTurretTile(BlockPos pos, BlockState state){ super(CCRegistry.CC_TURRET_TILE.get(), pos, state); }

  // ★ 禁止: rotationX/Y/neededRotationX/Y/clientNeededX/Y を再宣言しないこと(§9.1のAdam's地雷)。親フィールドを使う。
  // ★ 禁止: 3引数 tick(Level,BlockState,BlockPos) を override しないこと(§1.5)。無引数 tick() のみ。

  public IPeripheral getPeripheral(){ if(peripheral==null) peripheral=new TurretPeripheral(this); return peripheral; }
  public double getProjectileSpeed(){ return projectileSpeed; }
  public void setProjectileSpeed(double v){ projectileSpeed = Math.max(SPEED_MIN, Math.min(SPEED_MAX, v)); setChanged(); }
  public boolean getCreative(){ return creative; }
  public void setCreative(boolean b){ creative=b; setChanged(); }
  @Override public int getManaCost(){ return creative ? 0 : super.getManaCost(); }

  @Override public void tick(){                  // 無引数。ITickable経由(§1.5)
    super.tick();                                // ★必須: 親の server側旋回補間(実L74-91)を効かせる
    // 自律探索はJavaに置かない(頭脳=Lua)。発射は peripheral.fire() がメインスレで直接消化する。
  }

  // --- peripheral(mainThread=true ゆえメインスレ)からの発射要求。器に徹し標的判定はしない ---
  public boolean requestFire(){
    if (level == null || level.isClientSide) return false;
    long now = level.getGameTime();
    if (now - lastFireTick < MIN_FIRE_INTERVAL) return false;          // 1tick1発ガード
    if (getSpellCaster().getSpell().isEmpty()) return false;           // 未装填
    if (!(getBlockState().getBlock() instanceof CCTurret block)) return false;
    int cost = getManaCost();
    if (cost > 0 && !SourceUtil有効供給判定(cost)) return false;        // Source枯渇は事前にも弾く(§下)
    block.shootSpell((ServerLevel) level, getBlockPos());              // 正規ルート。Block#tickは使わない
    lastFireTick = now;
    return true;
  }

  // --- aim(BlockPos,Player) のVec3化(角度式は実L97-117と同一、Player依存処理は除去、updateBlock封印) ---
  public void aimVec(Vec3 target){
    if (level == null) return;
    Vec3 thisVec = Vec3.atCenterOf(getBlockPos());
    Vec3 diff = target.subtract(thisVec);
    Vec3 diff2D = new Vec3(diff.x, diff.z, 0);
    float ax = (float)(angleBetween(new Vec3(0,1,0), diff2D)/Math.PI*180.0);
    if (target.x < thisVec.x) ax = -ax;
    neededRotationX = ax + 90f;                  // 親フィールドへ書く
    Vec3 rotVec = new Vec3(diff.x, 0, diff.z);
    float ay = (float)(angleBetween(diff, rotVec)*180.0/Math.PI);
    if (target.y < thisVec.y) ay = -ay;
    neededRotationY = ay;
    setChanged();                                // ★updateBlock()は呼ばない(§6.3)。tickの0.1f補間で実回転が追従
  }

  // --- Lua向け read(mainThread=true でメインスレ実行される前提) ---
  public Map<Integer,Map<String,Object>> luaListEntities(double range){
    Map<Integer,Map<String,Object>> out = new HashMap<>();
    Vec3 c = Vec3.atCenterOf(getBlockPos()); int i=1;
    for (Entity e : level.getEntities(null, new AABB(getBlockPos()).inflate(range))){
      if (!(e instanceof LivingEntity)) continue;
      Vec3 dm = e.getDeltaMovement();
      Map<String,Object> m = new HashMap<>();
      m.put("uuid", e.getUUID().toString());
      m.put("type", ForgeRegistries.ENTITY_TYPES.getKey(e.getType()).toString()); // "minecraft:zombie"
      m.put("x", e.getX()); m.put("y", e.getY()); m.put("z", e.getZ());
      m.put("vx", dm.x);    m.put("vy", dm.y);    m.put("vz", dm.z);               // blocks/tick(§9.3 プレイヤー精度注意)
      m.put("distance", c.distanceTo(e.position()));
      m.put("isAlive", e.isAlive());
      m.put("isPlayer", e instanceof Player);
      out.put(i++, m);
    }
    return out;
  }
  // luaMuzzle/luaAimDir/luaAimError/luaMaxSingleSource も同様にメインスレ read として置く。
  // luaMaxSingleSource: SourceUtil の各 provider 供給量を評価し最大値を返す(§2.3注。合算しない)

  @Override public void saveAdditional(CompoundTag t){
    super.saveAdditional(t);                     // spellCaster + rotation系が乗る(継承・実L48-52,134-140)
    t.putDouble("projectileSpeed", projectileSpeed);
    t.putBoolean("creative", creative);
  }
  @Override public void load(CompoundTag t){
    super.load(t);
    projectileSpeed = t.contains("projectileSpeed") ? t.getDouble("projectileSpeed") : 1.5;
    creative = t.getBoolean("creative");
  }
}
```

### 7.3 NBT永続化の対象

| 永続項目 | 担当 |
|---|---|
| 装填スペル(spellCaster) | `BasicSpellTurretTile` が serialize/load(実L48-58。継承で乗る) |
| 旋回状態(rotationX/Y, neededRotationX/Y) | `RotatingTurretTile` が save/load(実L134-149。継承で乗る) |
| **projectileSpeed / creative** | 本MODで `super.saveAdditional(tag)` を**必ず先に呼んでから** put |

### 7.4 assets / data 最小セット(描画・監査medium反映)

`assets/arsccturret/` `data/arsccturret/`:
- `geo/cc_turret.geo.json` / `animations/cc_turret.animation.json` / `textures/…`(**新規・不可避**)。
- **`animations/cc_turret.animation.json` には "recoil" クリップが必須**: 継承した `BasicSpellTurretTile.walkPredicate`(実L67-73)が `thenPlay("recoil")` を参照する。**クリップが無いと GeckoLib が例外**。最小は空(0フレーム)クリップでも可。
- `blockstates/cc_turret.json`: GeckoLib描画なので variant 最小(`builtin/entity` 相当)。実体は GeoBlockRenderer。
- **GeoBlockRenderer 登録クラス(新規)**: client setup で `BlockEntityRenderers.register(CC_TURRET_TILE, ...)`。これが無いとブロック不可視/描画クラッシュ → 段2(設置)に入れない。**機能検証段階は無回転の最小 GeoModel + 最小 geo.json で弾道を先に通してよい**(回転追従 renderer の bone bind は§11)。
- `loot_tables/blocks/cc_turret.json`: self-drop 最小。
- `lang/en_us.json`,`ja_jp.json`: block名 + `alert.*` 流用。

### 7.5 mods.toml — 依存宣言

```toml
[[dependencies.arsccturret]]
  modId="forge";          mandatory=true; versionRange="[47,)";      ordering="NONE";  side="BOTH"
[[dependencies.arsccturret]]
  modId="minecraft";      mandatory=true; versionRange="[1.20.1,1.21)"; ordering="NONE"; side="BOTH"
[[dependencies.arsccturret]]
  modId="ars_nouveau";    mandatory=true; versionRange="[4.12.7,)";  ordering="AFTER"; side="BOTH"
[[dependencies.arsccturret]]
  modId="computercraft";  mandatory=true; versionRange="[1.116.1,)"; ordering="AFTER"; side="BOTH"  # cc-tweaked の modid は computercraft が正
```

> **同梱版突合手順(監査反映)**: 段1完了直後の `runClient` で `/mods` を開き、AllTheMods同梱CCの実 modid(`computercraft`)と実ビルド番号を突合 → `versionRange` をそれに合わせて確定する。同梱版が forge配布版とビルド番号違いだと mandatory 依存がロード拒否で本体起動しない(段2以前で詰む)ため、必要なら下限を緩める。

### 7.6 peripheral 配線(Forge1.20.1 + CC1.116.1)

`IPeripheralProvider` を `ForgeComputerCraftAPI.registerPeripheralProvider()`(非deprecated)で `FMLCommonSetupEvent` の `enqueueWork` 内に登録。

```java
@Mod.EventBusSubscriber(modid=CCRegistry.MODID, bus=Mod.EventBusSubscriber.Bus.MOD)
public class CcPeripheralSetup {
  @SubscribeEvent static void onSetup(FMLCommonSetupEvent e){
    e.enqueueWork(() -> ForgeComputerCraftAPI.registerPeripheralProvider(
      (world, pos, side) -> (world.getBlockEntity(pos) instanceof CCTurretTile tile)
          ? LazyOptional.of(tile::getPeripheral) : LazyOptional.empty()));
  }
}
```

> 依存は forge-api の `ForgeComputerCraftAPI`/`IPeripheralProvider`/`IPeripheral`/`LuaFunction` のみ。内部 `shared.Capabilities` には触れない。接続断(tile破壊後の wrap 参照)は CC 側が無効 peripheral として扱う([実機検証]: 破壊→再 wrap でエラーにならないか・§9.4)。

---

## 8. 一番危ない核心の検証順序(安いうちに甘さを潰す)

本実装の数百行に入る前に、この順で数十行ずつ潰す。各段は機械で白黒つく/目視1発で済む。最恐核心(deobf remap)とスレッド境界を**最小単独で先に**分離する(監査反映)。

**段0(ゲーム不要・最優先で並行可) — Lua偏差の純粋テスト**
`ballistics.lua` 単体を素のLua/craftos-pcで回し §3.6 の assert(`len(bullet-target)<0.5`)+クランプ境界ケースが全通ることを確認。

**段1a(機械で白黒・最恐核心を単独分離) — 空継承 Probe**
土台複製 → §4 の build.gradle(repositories=mavenCentral/Forge maven含む)/gradle.properties 反映 → `src` に **`public class Probe extends RotatingSpellTurret {}` 1ファイルだけ**置き compileJava。これが `BUILD SUCCESSFUL` = deobf/remap/座標/推移依存が**全部緑**(=最恐リスク消滅)。失敗時は §4.7 診断表で層を特定。

**段1b(機械で白黒) — 実体クラスの継承コンパイル**
`CCTurret`/`CCTurretTile`(aimVec/NBT/getShootAngle利用含む)を足して再 compileJava。段1aが緑なら、ここでの失敗は継承surface(メンバ可視性)に局所化され切り分けが1発でつく。

**段1.5(実機・最小・スレッド境界を段2より前に) — peripheral 1メソッド**
`listEntities` だけ実装した最小 peripheral を `runClient` で起動し、別コンピュータから `peripheral.wrap(...).listEntities()` を1回叩く。`@LuaFunction(mainThread=true)` でクラッシュせず table が返ることだけ確認。**[実機検証]**: `ipairs` で回るか。ここで CC スレッド同期方式を確定してから段2へ。

**段2(実機・目視1発) — 効果/VFXがタダで乗るか(委譲核心)**
クリエイティブで CCTurret を1個置き(`setCreative(true)` または近傍に十分な Source)、`Harm`(Projectile+Harm)を装填、`setProjectileSpeed(0.75)` で、5ブロック先の**静止した羊**に `aim`→`fire` を1回。確認:(1) 羊がダメージ = Effect が resolver 経由で乗る。(2) 着弾に色付きパーティクル = VFX が乗る。通らなければ `TileCaster`/`SpellContext`/`FakePlayer` 引数を本体 `RotatingSpellTurret.shootSpell`(実L62-68)と**1対1照合**。

**段2.5(実機・目視1発・往復恒等性) — aimVec↔getShootAngle(監査medium反映)**
**動く前に静止標的で**: `aim(P)`(=羊の静止座標)→収束(`getAimError≤tol`)→`fire` で **P に当たるか**。`aimVec` の角度逆算式と `getShootAngle`(pure luck式)が厳密な逆関数である保証はソース上に無いので、往復誤差を単独で切り分ける。許容外なら `aimTolDeg` を詰めるか、tile に最終 aim ベクトルを退避して onCast がそれを直接 `shoot` に使う変種を検討。

**段3(実機・目視1発) — 弾速=実速度=偏差一致(精度核心)**
**動く標的**(豚を等速で歩かせる)に対し、現在位置狙い→外す / 未来位置狙い(`P+V*(dist/s)`)→当たる、を1回見る。外れたら**まず単位(tick vs 秒=20倍)だけ疑う**。

**段4(実機) — スレッド安全 / 連射ガード / redstone封鎖**
2台同時アクセスでクラッシュしない。`fire()` 連打で1tick1発に収まり Source 枯渇で止まる。**隣に redstone 信号を与えても発射しない**(§6.1封鎖の確認)。

---

## 9. 未解決論点 / 参考元バグの非継承メモ

### 9.1 参考元(Adam's)から構造的に引き継がない地雷(実ソース確認済み)

- **フィールド再宣言(field shadowing)**: `AutoTurretTile` は `rotationX/rotationY/neededRotationX/Y/clientNeededX/Y` を**親と同名で再宣言**(実L58-63)し、`tick()` を `super.tick()` 呼びなしで丸ごと再実装(実L73〜)、`getShootAngle`/`saveAdditional` も自分の影フィールドを読む。親と二重化する脆い構造。**本MODは絶対に再宣言しない**(§7.2明記)。親フィールドをそのまま使い、**`super.tick()` を呼ぶ**(再宣言しないから親 tick がそのまま効くのが正しい因果・§1.5)。実装時に参考元を見て super 呼びを消す逆行をするな。
- **`setPlacedBy` の break 抜け**: Adam's(実L208-210)で `SOUTH` が `WEST` にフォールスルー(break無し)。継承元 `RotatingSpellTurret.setPlacedBy`(実L118-142)は正しい(SOUTH に break あり)ので、**override せず継承する**。
- **弾速 `0.5F` ハードコード(実L229) / LoS 整数間引き近似(実L251-269) / mode 0/1/2 の3固定**: どれも採用しない。
- **継承で正しいものを override し直さない**(育つチェックリスト相当): `setPlacedBy`/`getShootAngle`/`tick(無引数の親実装)`/`orderedByNearest`/`getDispensePosition` は override しない。うっかり override すると Adam's の罠を再現する。

### 9.2 仕様決定事項(ゆいくんが決める)

- **redstone 発射経路**: 初版で**塞ぐ**(§6.1で `Block#tick`/`neighborChanged` を空 override)。→ これは初版仕様として確定済み。残るのは「副入力として将来残すか」のみ。
- **Touch 初版要否**: 初版は Projectile のみ(§11)。
- **creative トグル / targetFilter 切替口**: peripheral 経由(`setCreative` 追加済み・§2.4)。物理アイテム右クリックは採らない。

### 9.3 実機検証で確定する項目(§Known Issues に集約)

(本文の各 [実機検証] を §Known Issues としてまとめる。重複記載を避ける。)

### 9.4 複数タレット(CIWS編成)

複数砲で同一標的を撃つ配分(集中 vs 分散)は上位Luaの仕事。**初版はタレット独立**(各自が独立に最寄りを撃つ)。接続断時(tile破壊後の wrap 参照)の挙動は[実機検証](§9.4・§7.6)。集中/分散は運用が固まってから上位レイヤとして足す(§11)。

---

## 10. ファイル構成(初版)

```
ars-cc-turret/                      ← 土台 ars-no-iframes 複製
  build.gradle / gradle.properties / settings.gradle / gradlew(.bat) / gradle/wrapper   ← 流用+§4反映
  src/main/java/com/yui/arsccturret/
    ArsCcTurret.java                ← @Mod エントリ。CCRegistry.init(bus)
    CCRegistry.java                 ← DeferredRegister(Block/Item/BlockEntityType)
    CCTurret.java                   ← extends RotatingSpellTurret(CC_BEHAVIOR_MAP + shootSpell override + redstone封鎖)
    CCTurretTile.java               ← extends RotatingTurretTile(弾速/NBT/aimVec/発射消化/Lua read)
    cc/
      TurretPeripheral.java         ← implements IPeripheral(@LuaFunction(mainThread=true) の口)
      CcPeripheralSetup.java        ← IPeripheralProvider 登録
    client/
      CCTurretRenderer.java         ← GeoBlockRenderer(初版は無回転最小可)
      ClientSetup.java              ← BlockEntityRenderers.register
  src/main/resources/
    META-INF/mods.toml              ← forge/minecraft/ars_nouveau/computercraft 依存宣言
    assets/arsccturret/…            ← blockstate/geo/animation(recoilクリップ必須)/texture/lang
    data/arsccturret/…              ← loot_table(self-drop)
  lua/turret/                       ← CC側(頭脳)。コンピュータに配置
    main.lua / config.lua / targeting.lua / ballistics.lua / turret.lua
```

初版スコープ: Projectile1発命中(段0〜3)まで。

---

## 11. 初版で作らないものリスト(否定リスト・実装の拾い食い防止)

哲学「土台は軽く小さく/準備の準備をするな」を構造で守る。下記は**段3命中実証後の追加層**であり、初版実装では一切手を出さない。

- **canFire()**(Lua が `isLoaded`/`getSource`/`getSpellCost` で合成)
- **autonomous フラグ一式**(Lua全制御で不要)
- **MethodTouch 対応**(初版は Projectile のみ)
- **fastestClose / 接近速度優先 / ロックチャタリング防止**(初版は nearest 固定)
- **二段リード**(`t_total = t_flight + t_rotate`)
- **重力対応 gravityLead**(isNoGravity=true ゆえ標準運用で不要)
- **LoS(視線遮蔽)判定**(撃って外れたら次標的フォールバックで代替)
- **GeoBlockRenderer の回転追従描画**(初版は無回転最小描画で弾道を先に通す)
- **複数砲の集中/分散配分**(初版は各砲独立)
- **プレイヤー速度の前tick位置差分フォールバック**(初版は対Mobスコープ。`getDeltaMovement` のみ)

これらに着手したくなったら、段3が緑になっているか・初版スコープを超える正規の載せ替えタイミングかを先に確認する。

---

## 12. 応用層（v1命中後に実装・2026-06-03〜）

> 「撃つエンジン(段0〜3)」を**実際に使える道具**に育てる層。当初 design はここを詳述してなかった（v1=1発命中で線引き）。ゆいくんの「設定も弄れない・wgetも無い・モニター表示も無い＝まだ設計通りじゃない」を受けて応用層として追加。実装済み。

### 12.1 見た目（Ars 純正 geo 流用）
- `getRenderShape` は親(`ENTITYBLOCK_ANIMATED`)のまま。`client/CCTurretModel`(GeoModel) が Ars 本体の `ars_nouveau:geo/spell_turret.geo.json` / `textures/block/spell_turret.png` / `animations/spell_turret_animations.json` を参照、`client/CCTurretRenderer`(GeoBlockRenderer) を `client/ClientSetup`(RegisterRenderers)で登録。tile は `BasicSpellTurretTile`(GeoBlockEntity+registerControllers)継承済みなので反動アニメも乗る。
- blockstate→particleモデル(Ars方式)、item は簡易フラットアイコン(BEWLR は後回し)。

### 12.2 標的優先は切替式（振り切らない）
- `targeting.priorities` に `nearest`(最寄り) と `fastestClose`(接近速度 `closeSpeed=-(V·(P-T))/|P-T|` 降順=脅威優先)。`config.priority` の名前で選択、実行時はモニタータップ＋`settings("turret.priority")`で切替。どちらかに固定しない。

### 12.3 火器管制アプリ構成
- `main.lua`(エントリ/統括): config+settings 読込 → 周辺機器解決 → `parallel.waitForAny(control, touch)`。
- `turret.lua`: `M.step(P,cfg,s,ballistics,targeting)` = 1tick の火器管制(純ロジック・lupaでテスト可)。状態 IDLE/TRACKING/FIRING/ESCAPING、火器管制ログ(TRK→SOL→FIRE)を蓄積。
- `monitor.lua`: CC モニターに 状態/標的(種別・距離・接近速度)/偏差解(LEAD座標・aim誤差・飛翔tick)/設定ボタン/火器管制ログ を 20Hz 描画。タップで priority/creative 切替。
- `config.lua`: 既定値。`settings(.turret)` が実行時上書き(永続)。

### 12.4 デプロイ（wget）
- `install.lua` が公開 raw(`raw.githubusercontent.com/jirachiuwu/ars-cc-turret/main/lua/`)から一式取得。導入: `wget run <install.lua の raw URL>` → `main` 実行。repo は public。

### 12.5 機械検証
- `lua/app_test.py`(lupa=本物のLua): 全 lua 構文チェック + `turret.step` 状態機械/ログ + `monitor.render` 無エラー。`lua/targeting_test.py`(優先則), `lua/ballistics_test.lua`(偏差)。CC-API ランタイムと見た目だけ実機/目視。

### 12.6 モニター GUI v2（火器管制ステーション・2画面）
> v1 モニターは単画面の読み取り＋2トグル。v2 は「ちゃんと設計を詰める」(ゆいくん)で2画面の操作卓に。

**枚数で縮退（モニター解決）:**
- **2枚** → MAIN 専用 ＋ CONFIG 専用（本命）。
- **1枚** → その画面に **タブ式**、上部の `[MAIN|CONFIG]` 切替ボタンで往復。
- **0枚** → ヘッドレス（制御だけ・従来）。

**役割割当:** 接続モニターを**名前ソート順**で `monitor_0`=MAIN / `monitor_1`=CONFIG（決定的）。`config.mainMonitor`/`config.configMonitor` に名前指定で上書き。各画面の隅に**自分の名前＋役割**を表示（どっちがどっちか一目）。タップ割当フローは作らない。

**MAIN 画面:** STATUS(色)／標的(種別・距離・接近速度)／偏差解(LEAD・aim誤差・飛翔t)／火器管制ログ(TRK→SOL→FIRE)。20Hz。

**CONFIG 画面:** トグルはピル、数値は増減。
- `PRIORITY [nearest][fastestClose]` / `CREATIVE [OFF][ON]`（選択中を反転）
- `SPEED [-] v [+]` / `RANGE` / `COOLDOWN` / `AIM TOL`（刻み・範囲は `config.steps`）
- タップで即反映（`setProjectileSpeed` 等）＋`settings(.turret)`永続。背景色ボタン、押下1フレーム反転フィードバック。

**ヒット判定:** render 時に `{x1,x2,y,action}` の領域表を構築 → `onTouch(monName,x,y)` が突合（描画と判定が必ず一致）。`monitor_touch` イベントの監視名で**どのモニターか**を判定（MAINのタップは無視 or 将来用、CONFIG/単画面のタップで設定変更）。

**検証(lupa):** clamp/step（境界・刻み）、座標→アクション、モニター解決(2/1/0枚→役割)、render 無エラー。見た目だけ目視。

### 12.7 即時照準（CIWS 連続射撃の核）
当初 `aimVec` は `neededRotationX/Y`(目標角)だけ書き、実回転は親 tick の `diff×0.1` 緩慢補間に任せていた(§6.3)。だが**動く標的では砲身が lead 点に追いつかず** `getShootAngle` がラグ→収束ゲート(`getAimError≤aimTolDeg`)が常に外れ「追従中ずっと撃てない／標的が止まってからしか撃たない」＝CIWS にならない。
→ **`aimVec` で現在角 `rotationX/Y` を目標へ即時スナップ**（高速サーボ相当）。`getShootAngle` が即 lead 点を向き、追従しながら `fireCooldownTicks` 間隔で連続射撃できる。視覚的な砲身の滑らかな旋回は捨てる（CC 制御砲なので即応を優先）。検証=実機目視（連続射撃の有無）＋ compileJava。

### 12.8 CONFIG モニターのスケール
MAIN は情報密度優先で `setTextScale(0.5)`、CONFIG は設定が少なく大きい方が見やすい/画面を埋めるので `1.0`。領域表は `getSize()` から算出するのでスケール差はタップ判定に影響しない。

### 12.9 標的モード（誰を狙うか・切替式）
設計要件「標的=敵/味方MOB・プレイヤー(任意)」を CONFIG の `TARGET` タップ巡回で実装。
- Java `listEntities` が `hostile = (e instanceof Enemy)` を事実報告（modded 敵も `Enemy` 実装なら拾う）。
- `targeting.makeFilter(mode)`: `hostile`(敵対のみ・既定) / `mobs`(非プレイヤー生物) / `all`(全部) / `players`(プレイヤーのみ)。全モード `isAlive and los` 前提。
- `config.targetMode` + `targetModes`(巡回順)。`settings("turret.target")` で永続。
- 検証(lupa): 各モードの包含/除外を assert。

### 12.10 計算と発射の独立（既に分離済み・確認）
制御ループは `updateInterval`(20Hz) 毎tickに「列挙→選択→偏差→照準(`P.aim`)」を計算し、`fire()` だけ `cooldown` でゲート。よって**発射間隔を伸ばしても計算/追従は 20Hz のまま落ちない**。1ループに入れてるのは「照準更新→引き金」の順序保証のため（別並行ループに割ると照準前発射の競合）。即時照準(§12.7)と合わせ、追従しながら独立した周期で連続射撃できる。VEL/LEADΔ パネルが発射の合間も更新し続けるのがその可視証拠。

### 12.11 バースト弾幕（連射の上限突破）
連射速度の限界は cooldown ではなく**ゲームの 20 tick/秒**＝単発は最速 20発/秒。それ以上の弾幕は**1トリガーで複数弾**で出す。
- `CCTurretTile.burst`(1..10, NBT, Lua可変) を追加。`onCast` で `burst` 発ループ、`spread=(burst-1)*0.06` を `shoot` の inaccuracy に渡す＝**Nが増えるほど自動で扇状に拡散**(burst=1 は spread0 で厳密命中＝従来どおり)。
- マナは shootSpell が1回だけ消費＝バーストは1トリガー分のコスト(安い弾幕)。
- `TurretPeripheral.getBurst/setBurst`、`config.burst` + `steps.burst`、CONFIG の `[-] BURST [+]`、`settings("turret.burst")`。
- 検証: compileJava + app_test(clampStep burst, CONFIG BURST タップ)。

### 12.12 プレイヤー速度＝位置差分（残像撃ち修正・§11の宿題を実装）
**プレイヤーの `getDeltaMovement()` はサーバ側でほぼ0**(移動がクライアント主導)。これだと listEntities の vx/vy/vz≈0 → リード≈0 → 現在座標を撃つ → 弾が着く頃には標的は先＝「残像撃ち」(MOBは getDeltaMovement が効くので命中していた)。
→ `CCTurretTile` に `velTrack(uuid→{prevPos,prevTick,vel})` を持ち、**位置の前tick差分から速度を出す**(`(pos-prevPos)/dt`)。初見のみ deltaMovement で暫定、次tickから差分。同tick再呼びはキャッシュ。範囲外は掃除。プレイヤー/MOD含め真の速度になりリードが効く。
- 注意: 標的が弾速 `s` より速いと `escapes()` で撃たない(追いつけない)→ 高速標的は SPEED を上げる。
- 検証: compileJava + 実機(VEL がプレイヤーの実速度を示す/リードが当たる)。

### 12.13 CONFIG スケール自動調整
項目が増えると固定スケールでは溢れ/小さすぎになる。`monitor.fitScale(needCols,needRows)` が **内容が収まる最大の `setTextScale`** を選ぶ(2→0.5を降順試行)。CONFIG は `setupFit(22,17)`。検証: lupa(サイズがスケール依存のモックで期待スケールを選ぶ)。

### 12.14 システム遅延補償 leadLag（残像撃ちの最終調整）
位置差分速度(§12.12)でリードは効くが、**最大弾速でも速い標的(走り/飛行)はギリギリ後ろ**になる。原因はセンサ→弾underway の遅延(弾は spawn 次tickから動く＋速度は前tick差分=半tick遅れ ≈ 1〜1.5tick)。その間に標的が `V*leadLag` 進む分が未補償＝残像。
→ turret.step で**標的位置を `V*leadLag` 先に進めてから lead** する(`Pc = Pp + V*lag`)。残量は速度比例なので全速度域で相殺。`config.leadLag`、CONFIG の `[-] LAG [+]` で微調整、`settings("turret.leadlag")`。Lua のみ=再起動不要。検証: lupa(leadLag>0 でリード量が増える)。

### 12.15 遅延の自動実測（固定値をやめる）
leadLag 固定だと残量が残る("惜しいけど後ろ")。真因は**遅延量が一定でない**こと: 制御ループは CC の mainThread 同期(getMuzzle/listEntities/aim/fire 等)で**毎tickちょうどに回らない**(数tickかかる)→照準がループ周期ぶん古くなる。
→ main.lua が `os.clock()` で**実測ループ周期**を出し `state.loopLag`[tick]に。turret.step の遅延 = `cfg.leadLag(基本spawn) + s.loopLag(実測)`。当てずっぽうの固定値でなく**実際の遅延に追従**。MAIN に `lag x.xt` を表示(透明化)。検証: lupa(loopLag が lead に加算、sol.lag=leadLag+loopLag)。
> さらに詰めるなら mainThread 呼び数を減らしてループ自体を速くする(can-fire 系 read を発射直前だけに)余地あり。

### 12.16 多角化（核の原則「一つの情報で計算するな」を適用）
固定 leadLag は手動補正＝その場しのぎ。核(育つチェックリスト)の「**一つの情報で判断/計算するな・多角的な情報から総合しろ**」(cc-fission-control の `err=min(複数の余裕)` と同型)を偏差計算に適用:
- **速度=複数サンプルの最小二乗**(`CCTurretTile.lsqVelocity`, VEL_SAMPLES=6): 単一差分のノイズを平滑、定常運動では厳密。位置の多角的情報。
- **遅延=実測ループ周期の EMA**(`main.lua` α=0.2): 瞬間値の jitter(「たまに先撃ち」)を除去。時刻の多角的情報。
- **手動 LAG は ±両方向の最終手段トリムに格下げ**(`leadLag` min=-3, 既定1=spawn定数)。誤差は計算の多角化で正し、ノブで埋めない。
検証: compileJava + 実機(走り/飛行に安定命中、先撃ちジッタ減)。

### 12.17 2次予測(曲線運動対応) + ループ高速化(scan集約)
1次(等速直線 `P+V·t`)は**曲線運動に弱い**(CIWS は曲線も追うべき)。多角化をもう一段:
- **加速度も使う**: `CCTurretTile.fit` が履歴を**2次最小二乗(放物線)フィット**して速度(1次)＋加速度(2次)を同時に出す(`ax/ay/az`, 暴れ防止に ±0.2 クランプ)。`ballistics.lead` に A を渡し **`future = P + V·t + 0.5·A·t²`**。曲線を予測。加速度が大きく intercept が無ければ t>maxT で撃たない(逃げ切り=正しい)。
- **ループ高速化**: lag 6.7t の主因は毎tick mainThread 同期 ~9回。`scan()` 一発に集約(muzzle+entities+speed+creative+cost+loaded+source)＋ `aim` が誤差も返す → **3回**に。lag 大幅減=補償量が減り精密化。
- 検証: app_test(2次で未来が曲がる/scan経由のstep)。実機(曲線標的への追従、lag低下)。

### 12.18 2次予測は撤回(荒ぶる)→1次に戻す。MAIN も自動サイズ
**実機で 2次予測(加速度)は不採用に。** lag 4t(サンプル間隔が広い)で finite-difference の加速度推定はノイズが激しく、`A·t²` が暴れて**偏差が荒ぶる/狙いが飛ぶ**。多角化の原則は「**有用な**多角情報」であって、ノイズを足すことではない。判断: 「すごく精度上がった」1次(線形最小二乗の平滑速度＋遅延補償)の方が良い→**速度=線形最小二乗に戻し ax/ay/az=0**(放物線フィット撤去)。曲線は追従ループの収束で吸収。土台で粘らず正規に戻す型。scan 高速化(§12.17)と aim-err は維持。
- **GUI 小さい頻発の修正**: MAIN を固定 `0.5` でなく `setupFit(26,14)` に。logSize を増やすと固定スケールでは小さく詰まる→**パネルが読める最大スケールを自動選択**、ログは残りを埋める。CONFIG/単画面も setupFit で統一。

### 12.19 CT(Coordinated Turn)予測の追加 — 曲線運動の本命対応
**動機**: §12.17(CA・2次予測)は §12.18 で撤回。だが「曲線で外れる=CV原理限界」は残った。CTモデル(等角速度旋回)は、CAと違い**1スカラー(ω)に集約**できるため、平滑が効く余地が大きい。同じ罠(ノイズ暴れ)を踏まないために**事前検証込み**で導入する。対象は**等速かつ等角速度で同じ弧を描く標的**(戦闘機・エリトラ旋回中・ターン中の数秒間)。ランダムジグザグや急機動は対象外(人間も予測できない、と割り切る)。

#### モデル定義(水平面のみCT・垂直はCV据え置き)
```
heading_n = atan2(vz_n, vx_n)             # 平滑速度から(生差分しない=ノイズ源を断つ)
ω_raw_n   = unwrap(heading_n - heading_{n-1})
ω         = moving_average(ω_raw, WINDOW) # 3〜5tick窓
v         = sqrt(vx² + vz²)

if |ω| > ε:                                # 旋回中
    φ  = heading + ω·t
    r  = v / ω                             # 符号付き旋回半径
    x(t) = P.x + r·(sin(φ) - sin(heading))
    z(t) = P.z - r·(cos(φ) - cos(heading))
else:                                      # CVフォールバック(自動)
    x(t) = P.x + vx·t
    z(t) = P.z + vz·t
y(t) = P.y + vy·t                          # 垂直は常にCV(初版非対応)
```
数学的に `lim_{ω→0} r·(sin(φ)-sin(h)) = v·t` に収束 → ε境界での不連続なし。

`unwrap`: `d = h_n - h_{n-1}; if d>π: d -= 2π; if d<-π: d += 2π`(±πジャンプ潰し)

#### 実装配置
- **Java側**(`CCTurretTile.trackVelocity` 拡張): `velHist` そのまま流用。新規 `headingHist`(uuid→ω履歴 deque)。平滑後の omega を `entities[i].omega` として返す。既存 `ax/ay/az=0` は撤去しない(§12.18 形維持=ワンタッチ撤退余地)。
- **Lua側**(`ballistics.lead` 拡張): 第7引数に omega 追加(後方互換: 省略時 0 → 純CV)。反復解ループ流用、predict式だけ切替。
- **設定**(`config.lua` に追加):
  ```lua
  ct = { enabled = true, window = 8, omegaEps = 0.02 }  -- ハーネスで機械決定済(下記参照)
  ```
- **撤退スイッチ**: `cfg.ct.enabled=false` でワンタッチ §12.18 状態に復帰。

**最終値の機械決定根拠**:
- `window=8`: S6(ω推定収束)≤12tick かつ (a)(b)(c)通過する WINDOW のうち最大。合成シナリオで(a)(b)(c)は全WINDOW通過するが、より長い WINDOW=より平滑=実機ノイズに強い。S6収束11tickは実用lag(4tick)の3倍以内で許容。
- `omegaEps=0.02`: (a)(b)(c)通過する eps の最大値。eps=0.05 にするとシナリオ3(ω=0.039)が閾値以下=CV化して命中率1%に転落。eps=0.02なら30秒一周より遅い旋回だけCV扱い=「ほぼ静止」判定として実用的。

#### テストハーネス(本実装の前にこれを切る・`lua/ct_harness_test.py`・lupa)
**合成シナリオ**(数学的妥当性=モデルの式が正しいことの担保):
1. 静止(ω=0, v=0)
2. 等速直線(ω=0, v=0.5 b/t 横切り)
3. 等速円旋回・遅い(一周160tick=8秒, 半径10, ω=0.039)
4. 等速円旋回・速い(一周60tick=3秒, 半径6, ω=0.105)
5. 過渡応答(直線30t → 旋回50t [一周100t, 半径8] → 直線30t) ※**参考表示のみ・閾値判定外**
6. ω推定収束テスト(直線10t → ω=0.125 旋回開始 → ω_est が ω_true·0.9 到達までの tick 数)

**WINDOW グリッドサーチ**: `[1,2,3,4,5,6,8]`
**omegaEps グリッドサーチ**: `[0.001, 0.005, 0.01, 0.02, 0.05]`

**命中判定**: `lead()` 戻りの予測点と「標的の実 (tick+t_flight) 位置」の誤差 < 0.5 block

**🟢機械判定撤退基準**(これに通らなければCT本実装に進まない):
- (a) シナリオ1,2 命中率 = 100%(CV互換性)
- (b) シナリオ3 命中率 ≥ 80%
- (c) シナリオ4 命中率 ≥ 50%
- (d) (a)(b)(c)を同時に満たす WINDOW が**1つ以上存在**
- (e) 既存 `ballistics_test.lua` 全PASS(後方互換)
- (f) `WINDOW` 機械決定: (a)(b)(c)通過 ∧ S6収束 ≤ 12tick のうち**最大WINDOW**を採用(=平滑優先)
- (g) `omegaEps` 機械決定: (a)(b)(c)通過する eps の**最大値**を採用(=最低限の旋回だけCV扱い)

シナリオ5は CT予測が「旋回が永遠に続く」前提のため、評価窓内に旋回終了tickが含まれると合成では原理的に外す(実機では旋回開始/終了の現実機動が連続するため意味が異なる)。閾値判定から外し、ω推定追従遅れの参考表示のみ。

(d)が不成立なら CT 自体撤回、design.md §12.20「CTも撤回」を追記して終わる(設計図を育てる)。

**実行結果(2026-06-05)**: 全20 PASS / 0 FAIL。
- (a) S1静止 100% / S2直線 100%
- (b) S3遅旋回 100%(CV比1%→CT 100%)
- (c) S4速旋回 96%(CV比0%→CT 96%)
- (d) 通過WINDOW = [1,2,3,4,5,6,8] 全部
- (f) WINDOW=8 (S6収束11tick)
- (g) omegaEps=0.02 (eps=0.05でS3が1%に転落するため0.02まで)

#### 実機録画は不採用
当初案では「ゆいくん実機録画 CSV → ハーネス再走」を最終ゲートに置いたが、以下の理由で**撤回**した:
- 合成5シナリオ + S6収束で WINDOW・omegaEps が🟢機械判定で確定済み(本実装前に決まる)
- マイクラ位置データは double 精度で連続的=合成と「位置ノイズ特性」が大差ない(差は標的の機動内容そのもので、それは目視で十分判定可能)
- 録画機構(環境変数/CSV出力/ON-OFF切替/ファイル受け渡し)を作る労力 > 得られる検証価値
- 実機での最終判定は**最後の砦(エリトラ目視・🔴1個)**で行う=合成で当たってるのに実機で外れるなら、その時点で原因切り分けは目視で十分可能

#### 撤退経路(CA撤回と同型)
- `cfg.ct.enabled=false` でワンタッチ CV 復帰。
- 撤回時は design.md §12.20「CTも撤回」を追記し、コード資産(heading履歴・omegaフィールド・ハーネス)は残す(§12.18 が A=0 を残してるのと同型)。

#### 🟢/🔴 仕分け (実機録画撤回後の最終版・2026-06-05)
| # | 項目 | 仕分け | 状態 |
|---|------|--------|------|
| 1 | 静止/直線 命中率100%(CV互換) | 🟢 | ✓ S1=100% / S2=100% |
| 2 | 遅い旋回 命中率≥80% | 🟢 | ✓ S3=100% |
| 3 | 速い旋回 命中率≥50% | 🟢 | ✓ S4=96% |
| 4 | (1)〜(3) 同時通過 WINDOW 存在 | 🟢 | ✓ 全WINDOW通過 |
| 5 | 既存 `ballistics_test.lua` 全PASS | 🟢 | ✓ 後方互換確認(`app_test.py` 51 PASS) |
| 6 | unwrap が ±π ジャンプを潰す | 🟢 | ✓ ハーネス通過 |
| 7 | ω<ε で CT予測 = CV予測 | 🟢 | ✓ 誤差<1e-9 |
| 8 | `ct.enabled=false` で §12.18 復帰 | 🟢 | ✓ omega=0 で完全一致 |
| 9 | `WINDOW` 機械決定(S6収束≤12) | 🟢 | ✓ **WINDOW=8** |
| 10 | `omegaEps` 機械決定 | 🟢 | ✓ **omegaEps=0.02** |
| 11 | compileJava 通る | 🟢 | 本実装後検証 |
| 12 | 実機エリトラ目視で「気持ちいい」 | 🔴 | 最後の砦(本実装後・最小化済み) |

**🟢 11個確定 + 1個本実装後 / 🔴 1個**(実機目視のみ・CLAUDE.md「最後の砦は僕」の主観1個)。シナリオ5は閾値判定から外し参考表示のみ(理由は撤退基準本文参照)。実機録画(R1/R2)は不採用に変更。

### 12.20 CT撤退 — 実機検証で「曲線で真逆」事故 → クランプ追加 → 効果不十分で default OFF
**実機目視(2026-06-06)**: 直線運動は dtCenter バグ修正後にちゃんと当たるようになった。だが**曲線運動で「真逆」を撃つ**現象が頻発(ゆいくん絵入りレポート: 弧を描く標的に対してリードが完全に逆方向)。

**真因(CSV解析で判明)**: CTモデルは数学的には正しく動いてた。バグじゃない。
- 実エリトラは「等速・等ωで弧を描き続ける」前提を満たさない
- ローカルに進行方向が連続的に変わる(ヨレを含む)動きをする
- lsq 平滑速度の heading 差分で ω を取ると、瞬間ヨレも拾って |ω|=0.3 rad/tick (=17°/tick) の過大値が頻発(実機CSV解析: mean|ω|=0.123, max|ω|=0.382)
- t_flight≈10tick なら ω·t ≈ 3rad ≈ 170° → 半周回った位置を予測 → 「真逆を撃つ」

**対策1: ω·t クランプ実装(§12.20)**: `ballistics.lead()` に `omegaTMax` 引数追加、|ω·te|>omegaTMax で角度クランプ(半径rは維持)。既定 π/4=45°。
- 合成シナリオでは全 omegaTMax 値で命中率不変(S1-S4 で ω·t<π/4 のため副作用なし=安全側導入の機械証明)
- 実機CSVシナリオ(距離5-30block・5点平均): CV=10.9% / CT(クランプ無)=9.1% / CT(クランプ有45°)=9.0%

**機械判定の結論**: 実機で **CV > CT**。クランプは「半周予測の事故」を防ぐが、それ以前にCTモデル自体がエリトラ標的に向いていない。
→ **`cfg.ct.enabled = false` を既定化(§12.18 状態に戻す)**

**コード資産は残置**:
- ω推定(Java `trackOmega`)、CT予測式(ballistics.lead omega引数)、クランプ(omegaTMax引数)、撤退スイッチ(ct.enabled)はすべて残す
- 将来 Mob の安定旋回(Phantom, Vex, Ghast 等)や、CT前提を満たす別標的タイプで再有効化可能
- `cfg.ct.enabled=true` でワンタッチ復帰

**実機CSVシナリオの恒久化**: 本案件以降、CT 系の判定は実機CSV(`turret.csv`)を取り込んだハーネスシナリオ8 で機械評価する。合成だけで判断しない(CLAUDE.md「合成PASS≠実機PASS」)。

#### 育つチェックリスト追記(案件CLAUDE.mdへ)
- **合成シナリオの前提が実機標的の物理特性に合うか確認**: 「等速・等ω」仮定するモデルは、実機標的(エリトラ等)がその仮定を満たさない場合、合成で当たっても実機で外す。設計確定前に「実標的の運動特性が仮定を満たすか」を1回確認する。本件の場合「エリトラは ローカルな進行方向ヨレを含む=等速ω仮定不成立」を事前に検出していれば、CT実装の労力を別の方向に向けられた。
