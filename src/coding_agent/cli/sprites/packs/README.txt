立绘包

把整个文件夹放到这里即可，不必改程序：

  ~/.wavecode/mascots/<包名>/
  <工作区>/.wavecode/mascots/<包名>/

启动时会创建这两个目录，并把发行包 default（idle/think/tool/err 的 GIF）复制进去。已有文件不覆盖。改工作区里的 default 即可换当前项目的立绘。

同名时：工作区覆盖用户目录，用户目录覆盖发行包。仍读取旧路径 ~/.wavemio/mascots/。

每个包一个文件夹，至少要有待机帧（idle.gif 或 idle.png 或 idle.txt）。放好后输入 /mascot，在列表里勾选。

包内文件。每个动作任选一种格式，同名时 GIF 优先于 PNG 优先于 txt：

  idle.gif / idle.png / idle.txt      待机，必需
  think.gif / think.png / think.txt   思考
  tool.gif / tool.png / tool.txt      调用工具
  ok.gif / ok.png / ok.txt            完成，可与 idle 相同
  err.gif / err.png / err.txt         出错
  palette.txt                         仅 txt 帧需要：一行一个  k=#RRGGBB

发行包 default 使用 GIF：idle 为待机，think 为问号，tool 为手写，err 为汗；ok 回退到 idle。
GIF 与 PNG 在终端绘制为 32×32 半块字符 ▀。GIF 按帧循环；非 32×32 的图缩放到画布。透明像素视为空白。

txt：32 行 × 32 列，每格一个调色板字母，`.` 为透明。以 # 开头的行是注释。
缺失的动作帧回退到 idle。纯 GIF 或 PNG 包可以没有 palette.txt。

idle / think / tool / ok / err 是包内动作帧文件名，不可用作包名。动作由任务状态自动切换。

切换：输入 /mascot 打开勾选列表。全屏用空格选择、Enter 确认；滚动 REPL 打印列表，不接受包名参数。
