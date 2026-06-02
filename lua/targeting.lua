-- targeting.lua — 標的選択。design.md §3.3。
-- 初版は nearest 固定 + 生存フィルタのみ。接近速度優先/ロックチャタリング防止/LoS は §11(初版で作らない)。
local M = {}

M.priorities = {
  nearest = function(a, b) return a.dist < b.dist end,
}

-- ents: listEntities() の戻り(1始まりIntキー table)。filter: e->bool。prioLess: (a,b)->bool。lockUuid: 追従中の uuid。
function M.select(ents, T, filter, prioLess, lockUuid)
  local cands = {}
  for _, e in ipairs(ents) do
    if e.isAlive and filter(e) then e.dist = e.distance; cands[#cands + 1] = e end
  end
  if #cands == 0 then return nil end
  if lockUuid then
    for _, e in ipairs(cands) do if e.uuid == lockUuid then return e end end  -- ロック継続(再選定でブレない)
  end
  table.sort(cands, prioLess)
  return cands[1]
end

return M
