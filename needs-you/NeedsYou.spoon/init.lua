--- === NeedsYou ===
---
--- A floating popup while a Claude Code session waits for you: a tool approval, AskUserQuestion, an MCP
--- prompt, or an approval gate in plain text. Part of the needs-you Claude Code plugin; its hook drives the
--- popup through two URLs:
---
---   hammerspoon://needs-you?session=…&kind=…&reason=…&title=…&pane=…&terminal=…&focused=0|1   show
---   hammerspoon://needs-you-clear?session=…                                                  close
---
--- One popup per session, stacked at the top centre of the main screen (top-right is where macOS banners
--- land). It floats above other windows, never takes keyboard focus and is not a notification, so Focus
--- modes don't hide it. Click: close it, focus the herdr pane (when there is one) and bring the terminal to
--- the front. Option-click: close only. A popup is skipped when the hook reports the herdr pane as focused
--- and that terminal is the frontmost app.
---
--- Usage in ~/.hammerspoon/init.lua:  hs.loadSpoon("NeedsYou"):start()

local obj = {}
obj.__index = obj

obj.name = "NeedsYou"
obj.version = "1.0.0"
obj.author = "Francisco J. Revoredo"
obj.homepage = "https://github.com/fjrevoredo/agent-skills/tree/main/needs-you"
obj.license = "MIT - https://opensource.org/licenses/MIT"

--- NeedsYou.width
--- Variable
--- Popup width in points.
obj.width = 380

--- NeedsYou.colors
--- Variable
--- Popup colours (hs.drawing.color tables): background, border, title, reason.
obj.colors = {
  background = { hex = "#1e1e2e", alpha = 0.96 },
  border = { hex = "#fab387" },
  title = { hex = "#cdd6f4" },
  reason = { hex = "#bac2de" },
}

--- NeedsYou.herdrPath
--- Variable
--- Path of the herdr binary, used to focus the pane on click. Default: the first existing of
--- ~/.local/bin/herdr and /opt/homebrew/bin/herdr; without one, a click only brings the terminal forward.
obj.herdrPath = nil

--- NeedsYou.defaultTerminal
--- Variable
--- Bundle id of the app a click brings forward when the hook didn't report the terminal.
obj.defaultTerminal = "com.github.wez.wezterm"

--- NeedsYou.popups
--- Variable
--- Open popups by session id: { canvas, kind, pane, terminal }. Read-only, for inspection
--- (`hs -c 'hs.inspect(spoon.NeedsYou.popups)'` once hs.ipc is loaded).
obj.popups = {}

local height, gap, margin = 74, 8, 16
local order = {} -- session ids, oldest first

local labels = {
  permission = "needs your approval",
  elicitation = "needs your input",
  gate = "waits for your OK",
}

local function valid(value, pattern)
  return value ~= nil and value ~= "" and value:match(pattern) ~= nil
end

local function validSession(s) return valid(s, "^%w[%w%._%-]*$") end
local function validPane(p) return valid(p, "^[%w:_%-]+$") end
local function validBundle(b) return valid(b, "^[%w%.%-]+$") end

local function fileExists(path)
  return path ~= nil and hs.fs.attributes(path, "mode") == "file"
end

function obj:_herdr()
  if fileExists(self.herdrPath) then return self.herdrPath end
  for _, path in ipairs({ os.getenv("HOME") .. "/.local/bin/herdr", "/opt/homebrew/bin/herdr" }) do
    if fileExists(path) then return path end
  end
  return nil
end

function obj:_layout()
  local frame = hs.screen.mainScreen():frame()
  for i, key in ipairs(order) do
    self.popups[key].canvas:frame({
      x = frame.x + (frame.w - self.width) / 2,
      y = frame.y + margin + (i - 1) * (height + gap),
      w = self.width,
      h = height,
    })
  end
end

function obj:_close(key)
  local popup = self.popups[key]
  if not popup then return end
  popup.canvas:delete()
  self.popups[key] = nil
  for i, k in ipairs(order) do
    if k == key then
      table.remove(order, i)
      break
    end
  end
  self:_layout()
end

function obj:_focus(popup)
  local terminal = validBundle(popup.terminal) and popup.terminal or self.defaultTerminal
  local function bringTerminal()
    if validBundle(terminal) then hs.application.launchOrFocusByBundleID(terminal) end
  end
  local herdr = validPane(popup.pane) and self:_herdr() or nil
  if herdr then
    -- No shell: the pane id is one argument, validated above.
    hs.task.new(herdr, function() bringTerminal() end, { "agent", "focus", popup.pane }):start()
  else
    bringTerminal()
  end
end

function obj:_show(key, params)
  self:_close(key)

  local width = self.width
  local canvas = hs.canvas.new({ x = 0, y = 0, w = width, h = height })
  canvas:level(hs.canvas.windowLevels.floating)
  canvas:behavior({ "canJoinAllSpaces", "stationary" })
  canvas:clickActivating(false)
  canvas:appendElements(
    {
      type = "rectangle",
      action = "strokeAndFill",
      fillColor = self.colors.background,
      strokeColor = self.colors.border,
      strokeWidth = 2,
      roundedRectRadii = { xRadius = 10, yRadius = 10 },
      trackMouseUp = true,
    },
    {
      type = "text",
      text = "● " .. params.title .. " " .. (labels[params.kind] or labels.elicitation),
      textColor = self.colors.title,
      textSize = 14,
      frame = { x = 14, y = 10, w = width - 28, h = 22 },
    },
    {
      type = "text",
      text = params.reason,
      textColor = self.colors.reason,
      textSize = 12,
      frame = { x = 14, y = 34, w = width - 28, h = 34 },
    }
  )

  local popup = { canvas = canvas, kind = params.kind, pane = params.pane, terminal = params.terminal }
  canvas:mouseCallback(function(_, message)
    if message ~= "mouseUp" then return end
    self:_close(key)
    if not hs.eventtap.checkKeyboardModifiers().alt then self:_focus(popup) end
  end)

  self.popups[key] = popup
  table.insert(order, key)
  self:_layout()
  canvas:show()
end

function obj:_onShow(params)
  if not validSession(params.session) then return end
  if params.focused == "1" and validBundle(params.terminal) then
    local front = hs.application.frontmostApplication()
    if front and front:bundleID() == params.terminal then
      self:_close(params.session)
      return
    end
  end
  self:_show(params.session, {
    kind = params.kind or "elicitation",
    reason = params.reason or "",
    title = (params.title ~= nil and params.title ~= "") and params.title or "Claude",
    pane = params.pane,
    terminal = params.terminal,
  })
end

--- NeedsYou:start()
--- Method
--- Binds the hammerspoon://needs-you and hammerspoon://needs-you-clear URLs.
function obj:start()
  if self._screenWatcher then self._screenWatcher:stop() end
  hs.urlevent.bind("needs-you", function(_, params) self:_onShow(params) end)
  hs.urlevent.bind("needs-you-clear", function(_, params)
    if validSession(params.session) then self:_close(params.session) end
  end)
  self._screenWatcher = hs.screen.watcher.new(function() self:_layout() end):start()
  return self
end

--- NeedsYou:stop()
--- Method
--- Unbinds the URLs and closes all popups.
function obj:stop()
  hs.urlevent.bind("needs-you", nil)
  hs.urlevent.bind("needs-you-clear", nil)
  if self._screenWatcher then
    self._screenWatcher:stop()
    self._screenWatcher = nil
  end
  for _, key in ipairs({ table.unpack(order) }) do self:_close(key) end
  return self
end

return obj
