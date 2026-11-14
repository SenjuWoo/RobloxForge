--!nocheck
-- A minimal DataModel for running the Luau that `rbforge push` sends, under Lune.
--
-- It models only what that code touches: services, FindFirstChild, Instance.new, Name/Parent,
-- Source, Clone, Destroy, game.PlaceId/Name and HttpService JSON. The point is to execute the real
-- generated text and observe the place afterwards, which a parser cannot do.
local serde = require("@lune/serde")

local children = setmetatable({}, { __mode = "k" })
local dataOf = setmetatable({}, { __mode = "k" })
local methods = {}

local function new(className)
	local data = { ClassName = className, Name = className, Archivable = true }
	if className == "Script" or className == "ModuleScript" or className == "LocalScript" then
		data.Source = ""
	end
	local obj
	obj = setmetatable({}, {
		__index = function(_, key)
			local m = methods[key]
			if m ~= nil then
				return m
			end
			return data[key]
		end,
		__newindex = function(_, key, value)
			if key == "Parent" then
				local old = data.Parent
				if old then
					local list = children[old]
					for i = #list, 1, -1 do
						if list[i] == obj then
							table.remove(list, i)
						end
					end
				end
				if value then
					children[value] = children[value] or {}
					table.insert(children[value], obj)
				end
			end
			data[key] = value
		end,
	})
	children[obj] = {}
	dataOf[obj] = data
	return obj
end

function methods.FindFirstChild(self, name)
	for _, child in children[self] or {} do
		if child.Name == name then
			return child
		end
	end
	return nil
end

function methods.GetChildren(self)
	return table.clone(children[self] or {})
end

function methods.Destroy(self)
	self.Parent = nil
end

function methods.Clone(self)
	if not self.Archivable then
		return nil
	end
	local copy = new(self.ClassName)
	for key, value in dataOf[self] do
		if key ~= "Parent" then
			copy[key] = value
		end
	end
	return copy
end

local http = new("HttpService")
http.Name = "HttpService"
function methods.JSONEncode(_, value)
	return serde.encode("json", value)
end
function methods.JSONDecode(_, text)
	return serde.decode("json", text)
end

game = new("DataModel")
game.Name = "Place1"
game.PlaceId = 0
http.Parent = game

function methods.GetService(self, name)
	local found = methods.FindFirstChild(self, name)
	if not found then
		found = new(name)
		found.Name = name
		found.Parent = self
	end
	return found
end

Instance = { new = new }
