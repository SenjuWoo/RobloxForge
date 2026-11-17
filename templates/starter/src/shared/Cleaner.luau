--!strict
-- One place to put everything that must end together: connections, instances, threads, callbacks.
-- Make one per character, per round, per open screen - and call :clean() when that thing ends.
-- Most leaks in Roblox games are a connection made per respawn that nobody disconnects.
--
--   local cleaner = Cleaner.new()
--   cleaner:add(humanoid.Died:Connect(onDied))
--   cleaner:add(effectPart)
--   character.Destroying:Connect(function() cleaner:clean() end)

local Cleaner = {}
Cleaner.__index = Cleaner

type Item = RBXScriptConnection | Instance | thread | () -> ()

export type Cleaner = typeof(setmetatable({} :: { items: { Item } }, Cleaner))

function Cleaner.new(): Cleaner
	return setmetatable({ items = {} }, Cleaner)
end

function Cleaner.add(self: Cleaner, item: Item)
	table.insert(self.items, item)
end

function Cleaner.clean(self: Cleaner)
	local items = self.items
	self.items = {}
	-- Newest first: things are torn down in the reverse of the order they were built.
	for index = #items, 1, -1 do
		local item = items[index]
		local kind = typeof(item)
		if kind == "RBXScriptConnection" then
			(item :: RBXScriptConnection):Disconnect()
		elseif kind == "Instance" then
			(item :: Instance):Destroy()
		elseif kind == "thread" then
			pcall(task.cancel, item :: thread)
		elseif kind == "function" then
			task.spawn(item :: () -> ())
		end
	end
end

return Cleaner
