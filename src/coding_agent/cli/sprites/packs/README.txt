立绘包（可替换）

每个包是一个目录，内含动作帧。把整个文件夹放进投放目录即可，不需要改程序。

投放目录（后者覆盖同名包）：

  1. 内置     安装包内 coding_agent/cli/sprites/packs/<包名>/
  2. 用户     ~/.wavecode/mascots/<包名>/     ← 请把自制包装这里
  3. 工作区   <工作区>/.wavecode/mascots/<包名>/
  兼容：仍会读取 ~/.wavemio/mascots/ 与 <工作区>/.wavemio/mascots/

包内文件（每个动作选一种，同名时 GIF 优先于 PNG 优先于 txt）：

  idle.gif / idle.png / idle.txt      待机（必需）
  think.gif / think.png / think.txt   思考
  tool.gif / tool.png / tool.txt      干活 / 调工具
  ok.gif / ok.png / ok.txt            完成（可与 idle 相同）
  err.gif / err.png / err.txt         出错
  palette.txt                         仅 txt 帧需要：一行一个  k=#RRGGBB

内置 default 用 GIF：idle＝待机，think＝问号，tool＝手写，err＝汗；ok 回退到 idle。
GIF / PNG：终端画成 32×32 半块字符 ▀。GIF 会按帧循环；不是 32×32 的图会缩放到画布。透明像素当空白。

txt：32 行 × 32 列，每格一个调色板字母，`.` 透明。以 # 开头的行是注释。
缺的动作帧会回退到 idle。纯 GIF / PNG 包可以没有 palette.txt。

idle / think / tool / ok / err 是包内动作帧文件名，不要拿来当包名。动作由任务状态自动切换，不用命令切换。

切换（全屏或 REPL）：

  /mascot                         列出可用立绘包与投放目录
  /mascot <包名>                  换包（例如 default）
