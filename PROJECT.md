# legend —— 独立项目

本项目从 zan-lang 仓库的 `templates/game/legend` 导出（导出日期：2026-10-20）。
语言仓库只放 SDK、公共包与**示例级**模板；产品级游戏在这里自己演进。

## 目录

    legend/
      client/      客户端：src/ assets/ data/ tools/，客户端用例在 client/tests/
      server/  服务端：源码、规则表副本、服务端工具
      tests/       跨端用例（同时读客户端与服务端）

所有命令都在**项目根**下执行（路径一律相对项目根）。

## 编译

```powershell
$env:ZAN_HOME = 'D:/path/to/zan-lang'   # 编译器与 stdlib 同源
pwsh -File client/tools/build.ps1
```

ZAN_HOME 指向 zan-lang 仓库时用它的 `build/zanc.exe` 与 `stdlib/`；
不设则用 PATH 上的 `zanc`。stdlib 也可用 ZAN_STDLIB 单独指定。
### 单文件发布

发一个自包含 exe（资源内嵌、GUI 驱动静态链接，exe 旁边不需要 assets/skins/data）：

```powershell
pwsh -Command "& 'client/tools/build.ps1' -ZancArgs @('--publish','--link-mode','static')"
```

- `--publish`：内嵌 assets 资源并做发布级优化（实测 405 files → 36MB exe）。
- `--link-mode static`：把 zan_gui / zan_image 驱动静态链接进 exe；
  默认 `shared` 会在 exe 旁放两个 dll，那就不是单文件。
- 自检：把 exe 旁的 `zan_gui.dll` / `zan_image.dll` 挪走再启动，能起来即为真单文件。

## 公共包

包从三处解析：`<项目根>/packages/`、`<项目根>/.zan-packages/`、
全局 `%LOCALAPPDATA%\Zan\packages`。需要某个包时：

```powershell
Copy-Item -Recurse <zan-lang>/packages/<Name> packages/<Name>
```

或编译时加 `--package-project <zan-lang>`（直接吃仓库里的 packages/）。

## 测试

```powershell
pwsh -File client/tools/test.ps1     # 客户端用例（Python 回归 + 无头模型用例）
python tests/test_rules_sync.py      # 跨端用例（规则表同步）
```

## 服务端

服务端规则表由客户端数据单向同步：

```powershell
python server/tools/sync_rules.py            # 同步
python server/tools/sync_rules.py --check    # 只校验漂移
```

### 服务端凭据

服务端工程 `server/` **不在仓库里带任何可用凭据**：`config/app.json` 的
`[auth].secret`（会话 Cookie 签名密钥，引擎要求 ≥32 字符）与
`[auth].bootstrapPassword`（空库首启种出 `admin` 的种子口令，要求 ≥12 字符）
都留空。留空是引擎设计的 fail-closed 状态——发不出管理员会话 Cookie，空库也不会
种出带已知口令的管理员账号。

本地开发用 `server/tools/dev_env.py` 生成随机会话密钥与种子口令，写进 gitignore
的 `server/data/.dev-secrets.json`，再以环境变量（`ZAN_AUTH_SECRET` /
`ZAN_BOOTSTRAP_ADMIN_PASSWORD`）注入服务端进程——引擎的 `Cfg.ApplyEnv` 在读文件
之后执行，环境变量优先于文件。`server/tools/e2e.py`、`sec_probe.py`、
`e2e_legend.py` 的管理员口令同样从这份本地文件读取。

```powershell
python server/tools/dev_env.py init      # 只生成（可重复执行）
python server/tools/dev_env.py show      # 打印当前生效的密钥与口令
python server/tools/dev_env.py launch    # 带凭据起服
```

公网部署必须覆盖这两个值，并同步覆盖 `[game].gatePass` 与客户端侧的加密共享
密钥（否则客户端与服务端对不上）。详见 `server/README.md` 的「凭据模型」一节。