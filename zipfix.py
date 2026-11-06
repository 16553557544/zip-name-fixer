#!/usr/bin/env python3
"""zipfix - 修复压缩包里的中文文件名乱码。

原理: 压缩包里的文件名是字节。乱码不是文件坏了, 是解压软件用错了编码去解释
这些字节。这个脚本把字节读出来, 挨个用候选编码解一遍, 按"像不像正常文件名"
打分, 选最合理的那个, 再按 UTF-8 重新打包。

用法:
    python zipfix.py list  <压缩包>            只列出会怎么改
    python zipfix.py check <压缩包>            只报有几处乱码, 有问题退出码=1
    python zipfix.py fix   <压缩包> [-o 新文件] 生成修好的压缩包
    python zipfix.py fix   <压缩包> --inplace  直接覆盖原文件
"""

import argparse
import io
import os
import sys
import zipfile

# 候选编码: 覆盖中文 Windows / 日文 Windows / 韩文 / 繁体 / 现代 UTF-8
CANDIDATES = ["utf-8", "gb18030", "big5", "cp932", "euc-kr", "cp437"]

# 打分阈值: 收益必须比原名字高出这么多才认为值得改, 避免把正常名字改坏
MIN_GAIN = 3

# 高频常用字 + 文件名里常见词。GBK 和 Shift-JIS 的字节范围有重叠,
# 光"能解码成汉字"分不出对错, 得看解出来的是不是正常人会用的字。
COMMON = set(
    "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工"
    "也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小"
    "物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形"
    "相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建"
    "月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长"
    "求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战"
    "先回则任取据处书面测试验证名称压缩包文档图片视频音频表格数据报告说明记录笔记教程源码"
    "项目设计资料照片截图安装下载最新完整中文英文日文样本示例模板格式备份合同发票简历作业"
    "教材课件论文手册指南清单目录路径扩展编码字体颜色背景边框按钮页面标题章节附录参考"
    "输入输出结果过程方法步骤注意事项要求规则标准显示设置修改删除新增查询统计分析汇总"
    "明细客户供应商产品商品价格折扣优惠活动会员积分余额支付退款税费财务会预算成本利润"
    "损失资产负债现金流投资融资股票基金保险贷款利率汇率市场行业竞争战略目标任务进度"
    "计划安排分配协调沟通会议纪要通知公告新闻媒体报评论观点意见建议反馈问题答案解决"
    "技术工具平台环境配置参数默认自定义扩展插件模块组件接口调用函数变量对象数组字符"
    "串整数浮点布尔条件循环判断返回异常错误调试性能优化重构覆盖仓库分支合并冲突提交"
    "推送拉取克隆版本发布打包升级降级迁移同步权限认证加密解密签名证书域名端口防火墙"
    "代理缓存队列线程进程内存磁盘网卡显卡处理器主板电源风扇温度噪音散热清灰维修保养"
    "故障保修保养相机手机电脑平板笔记本台式一体服务器工作站交换机路由器摄像头打印机"
    "扫描仪键盘鼠标显示器耳机音箱话筒投影幕布白板笔纸张文件夹订书机裁纸刀打孔碎纸过塑"
    "装订复印传真电话机U盘硬盘光驱刻录光盘内存条显卡声卡网卡读卡器数据线充电器电池"
    "笔记本台式机主机屏幕键盘鼠标垫散热支架底座外接扩展坞转换头适配器接头线材配件"
    "说明保修卡订单物流快递签收评价售后咨询在线客服人工智能机器人自动回复关键词知识库"
    "图表曲线柱状饼图折线散点雷达热力地图词云树状漏斗仪表盘进度条滑块开关下拉菜单弹窗"
    "对话框提示信息加载中请稍候失败成功重试取消确定是否上一步下一步完成跳过帮助设置退出"
    "关闭打开折叠展开搜索筛选排序分组标签分类备注描述详情简介主页首页末页返回前进刷新"
    "全屏最小化最大化还原拖拽点击双击右键左键滚轮手势滑动缩放旋转翻转裁切复制粘贴剪切"
    "撤销重做全选查找替换格式刷排版字号行距对齐缩进项目符编号插入图表公式透视排序条件"
    "数据验证保护冻结隐藏工作表单元格行列合并拆分底纹粗体斜体下划线删除线上标下标超链接"
    "批注页眉页脚分页打印预览导出为另存保存关闭退出打开新建最近桌面文档下载安装包镜像"
    "驱动程序软件硬件系统工具实用小辅助增强主题皮肤壁纸屏保锁桌面图标任务栏开始菜单"
    "通知中心消息邮件短信联系人地址簿日历备忘录音记事本计算器翻译字典百科搜索引擎浏览器"
    "网页链接书签历史缓存登录注册账号密码头像昵称签名状态朋友关注粉丝点赞收藏转发"
    "评论私信群聊通知公告活动投票抽奖红包礼物祝福生日节日聚餐旅行出差机票酒店景点门票"
    "路线攻略游记短视频音乐电影电视剧综艺动漫小说漫画游戏赛事比分球队球员教练训练健身"
    "跑步骑行游泳瑜伽减肥食谱菜普食材调料做法火候时间分量营养热量搭配早餐午餐晚餐夜宵"
    "甜点饮品咖啡茶酒水果蔬菜肉蛋奶米面油盐酱醋糖辣咸酸甜苦香鲜麻脆软硬嫩老新旧大小"
    "多少高低长短宽窄厚薄轻重快慢早晚冷热干湿明暗亮黑白红黄蓝绿紫橙粉灰棕金银彩色单双"
    "左右上下前后里外中间旁边角顶底头尾首末初终开始结束起止来去回走跑停站坐躺睡醒吃喝玩"
    "笑哭说读写听看闻摸想记忘学教导问答帮救给拿放丢捡买卖送收寄带借还换修造建拆装卸搬"
    "推拉抬举扛抱握抓捏拍打敲踢跳爬游飞落升降转弯直曲圆方尖平斜横竖正反内外"
)


def score(text):
    """给一个解码结果打"像不像正常文件名"的分。

    判据不是"CJK 多就给高分"——GBK 和 Shift-JIS 能互相解出汉字, 那样会判定错误。
    只有解出人和常用字(或假名/韩文/可打印 ASCII)才给高分, 解出一堆生僻字只给很少分。
    """
    good = 0
    bad = 0
    for ch in text:
        code = ord(ch)
        if ch in COMMON:                   # 高频常用字
            good += 4
        elif 0x4E00 <= code <= 0x9FFF:     # 其他汉字: 可能是生僻字, 也可能只是没收录
            good += 1
        elif 0x3040 <= code <= 0x30FF:     # 日文假名: 中文文件名里不会出现
            good += 5
        elif 0xAC00 <= code <= 0xD7AF:     # 韩文音节
            good += 4
        elif 0x3400 <= code <= 0x4DBF:     # 汉字扩展 A
            good += 1
        elif code < 0x20 or code == 0x7F:  # 控制字符
            bad += 6
        elif 0xE000 <= code <= 0xF8FF:     # 私用区
            bad += 6
        elif code == 0xFFFD:               # 替换符, 解码失败留下的
            bad += 6
        elif 0x2500 <= code <= 0x257F:     # 制表符区: GBK 字节被 cp437 解出来的样子
            bad += 2
        elif code < 0x80:                  # 可打印 ASCII
            good += 1
    return good - bad


def raw_bytes(name, flag_bits):
    """把 zipfile 解出来的字符串还原成文件里的原始字节。

    没打 UTF-8 标志位时, zipfile 按 cp437 解码, 这里反向往回转。
    """
    if flag_bits & 0x800:
        return name.encode("utf-8")
    try:
        return name.encode("cp437")
    except UnicodeEncodeError:
        return name.encode("utf-8", "surrogateescape")


def best_guess(name_bytes):
    """在候选编码里挑一个最像正常文件名的。返回 (新名字, 编码, 得分)。"""
    original = name_bytes.decode("cp437", "replace")
    best = (original, "cp437", score(original))
    for enc in CANDIDATES:
        try:
            text = name_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        s = score(text)
        if s > best[2]:
            best = (text, enc, s)
    return best


def analyse(path):
    """返回需要改名的条目列表。"""
    changes = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.filename.endswith("/"):
                continue
            b = raw_bytes(info.filename, info.flag_bits)
            if info.flag_bits & 0x800:
                continue  # 已标明 UTF-8, 不用管
            new, enc, new_score = best_guess(b)
            old_score = score(info.filename)
            if new_score - old_score >= MIN_GAIN and new != info.filename:
                changes.append((info, new, enc))
    return changes


def cmd_list(path):
    changes = analyse(path)
    if not changes:
        print("没有发现文件名乱码。")
        return 0
    print("发现 %d 处文件名乱码:\n" % len(changes))
    for info, new, enc in changes:
        print("  %s\n    -> %s   (按 %s 解出)" % (info.filename, new, enc))
    return 0


def cmd_check(path):
    changes = analyse(path)
    if changes:
        print("有 %d 处文件名乱码。运行 `python zipfix.py list %s` 看细节。"
              % (len(changes), os.path.basename(path)))
        return 1
    print("没有发现文件名乱码。")
    return 0


def cmd_fix(path, out, inplace):
    changes = analyse(path)
    if not changes:
        print("没有发现文件名乱码，不用改。")
        return 0

    target = path if inplace else (out or (os.path.splitext(path)[0] + "-fixed.zip"))
    if inplace:
        target = path + ".tmp"

    with zipfile.ZipFile(path) as src:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
            mapping = {info.filename: new for info, new, _ in changes}
            for info in src.infolist():
                data = src.read(info.filename)
                name = mapping.get(info.filename, info.filename)
                zi = zipfile.ZipInfo(name, date_time=info.date_time)
                zi.external_attr = info.external_attr
                zi.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(zi, data)

    if inplace:
        os.replace(target, path)
        target = path

    print("已修复 %d 个文件名，输出: %s" % (len(changes), target))
    for _, new, enc in changes:
        print("  " + new)
    return 0


def main():
    ap = argparse.ArgumentParser(
        prog="zipfix",
        description="修复 zip 压缩包里的中文/日文/韩文文件名乱码。")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name, hlp in (("list", "列出会怎么改"), ("check", "只检查有没有乱码")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("archive")

    p = sub.add_parser("fix", help="生成修复后的压缩包")
    p.add_argument("archive")
    p.add_argument("-o", "--out", help="输出文件路径")
    p.add_argument("--inplace", action="store_true", help="直接覆盖原文件")

    args = ap.parse_args()
    if not os.path.exists(args.archive):
        print("找不到文件: %s" % args.archive, file=sys.stderr)
        return 2

    try:
        if args.cmd == "list":
            return cmd_list(args.archive)
        if args.cmd == "check":
            return cmd_check(args.archive)
        return cmd_fix(args.archive, args.out, args.inplace)
    except zipfile.BadZipFile:
        print("这不是一个有效的 zip 文件: %s" % args.archive, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
