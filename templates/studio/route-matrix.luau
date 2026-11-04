--!strict
-- Walkability proof. Run in the Server datamodel during Play, after the world is built.
-- Every route uses the real agent size; list each objective from every entry so one-sided blockers show up.
-- Target: failures == 0. Labels make the report readable without a screenshot.
local PathfindingService = game:GetService("PathfindingService")
local AGENT = { AgentRadius = 2, AgentHeight = 6, AgentCanJump = false }

local entries: { [string]: Vector3 } = {
	-- Spawn = Vector3.new(0, 5, 0),
}
local objectives: { [string]: Vector3 } = {
	-- Workbench = Vector3.new(20, 5, 10),
}

local report = { routes = 0, failures = {} :: { string } }
for eName, a in entries do
	for oName, b in objectives do
		local path = PathfindingService:CreatePath(AGENT)
		local ok, err = pcall(function()
			path:ComputeAsync(a, b)
		end)
		report.routes = report.routes + 1 -- no compound assignment: the MCP pre-parser rejects it
		if not ok or path.Status ~= Enum.PathStatus.Success then
			table.insert(
				report.failures,
				string.format(
					"%s -> %s: %s",
					eName,
					oName,
					if ok then path.Status.Name else tostring(err)
				)
			)
		end
	end
end
return game:GetService("HttpService"):JSONEncode(report)
