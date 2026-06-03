-- targeting.lua — 標的選択。design.md §3.3。
-- 初版は nearest 固定 + 生存フィルタのみ。接近速度優先/ロックチャタリング防止/LoS は §11(初版で作らない)。
local M = {}

M.priorities = {
  nearest      = function(a, b) return a.dist < b.dist end,         -- 最寄り優先(design v1既定)
  fastestClose = function(a, b) return a.closeSpeed > b.closeSpeed end,  -- 接近速度(closing)優先=CIWS的に脅威優先
}

-- ents: listEntities() の戻り(1始まりIntキー table)。T: 砲口{x,y,z}。filter: e->bool。prioLess: (a,b)->bool。lockUuid: 追従中の uuid。
function M.select(ents, T, filter, prioLess, lockUuid)
  local cands = {}
  for _, e in ipairs(ents) do
    if e.isAlive and filter(e) then
      e.dist = e.distance
      -- 接近速度 = 砲口Tへ距離が縮む速さ = -(V·(P-T))/|P-T|。正=接近, 負=後退。fastestClose 用。
      local dx, dy, dz = e.x - T.x, e.y - T.y, e.z - T.z
      local d = math.sqrt(dx * dx + dy * dy + dz * dz)
      e.closeSpeed = (d > 1e-6) and -((e.vx * dx + e.vy * dy + e.vz * dz) / d) or 0
      cands[#cands + 1] = e
    end
  end
  if #cands == 0 then return nil end
  if lockUuid then
    for _, e in ipairs(cands) do if e.uuid == lockUuid then return e end end  -- ロック継続(再選定でブレない)
  end
  table.sort(cands, prioLess)
  return cands[1]
end

return M
