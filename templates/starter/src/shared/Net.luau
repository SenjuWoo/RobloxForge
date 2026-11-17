--!strict
-- Every remote the game has, named in one list. The server creates them; the client waits for them.
-- A remote that is not in this list does not exist, which keeps typos from becoming silent bugs
-- and gives a reviewer the whole attack surface in one screen.
--
-- A remote carries an INTENT ("I pressed the action button", "buy this upgrade id"), never a result
-- ("give me 50 coins"). The server decides what the intent is worth.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Net = {}

-- Client -> server requests.
Net.Events = {
	"DoAction", -- no arguments
	"BuyUpgrade", -- (upgradeId: string)
}

local FOLDER = "Remotes"

-- Server only, once, before any service starts.
function Net.setup()
	assert(RunService:IsServer(), "Net.setup is server-only")
	local folder = Instance.new("Folder")
	folder.Name = FOLDER
	for _, name in Net.Events do
		local remote = Instance.new("RemoteEvent")
		remote.Name = name
		remote.Parent = folder
	end
	folder.Parent = ReplicatedStorage -- parent last: the client sees the folder complete
end

function Net.event(name: string): RemoteEvent
	assert(table.find(Net.Events, name), "unknown remote: " .. name)
	local folder = ReplicatedStorage:WaitForChild(FOLDER)
	return folder:WaitForChild(name) :: RemoteEvent
end

return Net
