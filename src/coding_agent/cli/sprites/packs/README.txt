立绘包（可替换）

每个包是一个目录，内含五个动作帧。搜索顺序（后者覆盖同名包）：

  1. 内置   coding_agent/cli/sprites/packs/<包名>/
  2. 用户   ~/.wavemio/mascots/<包名>/
  3. 工作区 <工作区>/.wavemio/mascots/<包名>/

包内文件（每个动作二选一，同名时 PNG 优先）：

  idle.txt / idle.png      待机
  think.txt / think.png    思考
  tool.txt / tool.png      干活 / 调工具
  ok.txt / ok.png          完成
  err.txt / err.png        出错
  palette.txt              仅 txt 帧需要：一行一个  k=#RRGGBB

内置 default 是五张空白 24×24 PNG，方便直接覆盖。
PNG：必须是 24×24、8 位、非隔行。RGB / RGBA / 索引色均可。透明像素（alpha=0）当空白。
终端不会贴原图，会把像素编成半块字符 ▀。不要用别的尺寸，不会自动缩放。

txt：24 行 × 24 列，每格一个调色板字母，`.` 透明。以 # 开头的行是注释。
缺的动作帧会回退到 idle。纯 PNG 包可以没有 palette.txt。

idle / think / tool / ok / err 是动作名，不要拿来当包名。

切换（全屏或 REPL）：

  /mascot                         列出包与当前动作
  /mascot <包名>                  换包（例如 default）
  /mascot idle|think|tool|ok|err  换动作帧
