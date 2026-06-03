-- install.lua — ars-cc-turret の Lua 一式を公開 GitHub から取得。
-- どのコンピュータでも: wget run https://raw.githubusercontent.com/jirachiuwu/ars-cc-turret/main/lua/install.lua
local BASE  = "https://raw.githubusercontent.com/jirachiuwu/ars-cc-turret/main/lua/"
local FILES = { "ballistics.lua", "targeting.lua", "config.lua", "turret.lua", "monitor.lua", "main.lua" }

local fails = 0
for _, f in ipairs(FILES) do
  local r = http.get(BASE .. f)
  if r then
    local h = fs.open(f, "w"); h.write(r.readAll()); h.close(); r.close()
    print("ok   " .. f)
  else
    print("FAIL " .. f); fails = fails + 1
  end
end

if fails == 0 then
  -- 自動起動: 再起動/チャンク再読込でタレットが自動再開(防衛装置として完成形)。不要なら startup を削除。
  local h = fs.open("startup.lua", "w")
  h.write('shell.run("main")\n')
  h.close()
  print("installed (+startup). run:  main")
else
  print(fails .. " file(s) failed. http 有効か URL を確認。")
end
