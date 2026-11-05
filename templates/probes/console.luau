-- probe: console
-- datamodel: any
-- params: limit=30 include="error" since=0
-- purpose: The output log, deduplicated and counted, newest last. include = "error" (errors only), "warn" (errors
--   and warnings) or "all". since = only the last N seconds (0 = whole session) - use it right after a change so old
--   errors do not read as new. Zero NEW errors is the gate.
local LIMIT, include, since = {{limit}}, {{include}}, {{since}}
local cutoff = if since > 0 then os.time() - since else 0
local want = {
	[Enum.MessageType.MessageError] = true,
	[Enum.MessageType.MessageWarning] = include ~= "error",
	[Enum.MessageType.MessageOutput] = include == "all",
	[Enum.MessageType.MessageInfo] = include == "all",
}
local seen, order = {}, {}
for _, e in game:GetService("LogService"):GetLogHistory() do
	if want[e.messageType] and (e.timestamp or 0) >= cutoff then
		local key = e.message:gsub("%d+%.%d+", "#"):sub(1, 220)
		if not seen[key] then
			seen[key] = { n = 0, kind = e.messageType.Name:gsub("Message", ""), text = e.message:sub(1, 300) }
			table.insert(order, key)
		end
		seen[key].n += 1
	end
end
local out = { string.format("%d distinct %s message(s)%s", #order, include, if since > 0 then " in the last " .. since .. " s" else "") }
for i = math.max(1, #order - LIMIT + 1), #order do
	local s = seen[order[i]]
	table.insert(out, string.format("%-7s x%-3d %s", s.kind, s.n, s.text))
end
return table.concat(out, "\n")
