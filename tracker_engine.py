"""OoT progress evaluator, reachability engine, and region-transition alert generator."""
from dataclasses import dataclass, field
from typing import Any

CAP_LABELS_ZH = {
    "child": "幼年形态",
    "adult": "成年形态",
    "sword": "剑",
    "deku_stick": "德库木棒",
    "slingshot": "妖精弹弓",
    "boomerang": "回旋镖",
    "bomb": "炸弹袋",
    "hammer": "百万吨锤",
    "bow": "妖精之弓",
    "hookshot": "钩索",
    "longshot": "长钩索",
    "iron_boots": "铁靴",
    "hover_boots": "浮空靴",
    "goron_bracelet": "鼓隆手环",
    "silver_gauntlets": "银护手",
    "golden_gauntlets": "金护手",
    "bottle": "空瓶",
    "magic": "魔力槽",
    "dins_fire": "迪荧之火",
    "fire_arrow": "火箭",
    "ocarina": "时之笛/妖精之笛",
    "zelda_lullaby": "塞尔达摇篮曲",
    "lullaby": "塞尔达摇篮曲",
    "epona": "伊波娜之歌",
    "epona_adult": "成年骑乘伊波娜",
    "saria": "莎莉亚之歌",
    "sun_song": "太阳之歌",
    "song_of_time": "时之歌",
    "storm_song": "岚之歌",
    "minuet": "森之小步舞曲",
    "bolero": "火之波丽露舞曲",
    "serenade": "水之小夜曲",
    "requiem": "魂之慰灵曲",
    "nocturne": "暗之梦幻曲",
    "scarecrow": "稻草人之歌",
    "scarecrow_longshot": "长钩索 + 稻草人之歌",
    "zora_tunic": "卓拉服",
    "goron_tunic": "鼓隆服",
    "silver_scale": "银鳞片",
    "gold_scale": "金鳞片",
    "magic_bean": "魔法豆",
    "bean_lw01": "幼年在此草坪种下魔法豆",
    "bean_lh": "幼年在湖畔实验室旁种下魔法豆",
    "bean_gy": "幼年在墓地软土种下魔法豆",
    "bean_dmt": "幼年在多东哥洞窟口前种下魔法豆",
    "bean_dmc": "幼年在火山口传送点种下魔法豆",
    "bean_dc": "幼年在巨大邪神像门前种下魔法豆",
    "zelda_letter": "塞尔达的信",
    "gerudo_card": "格鲁德会员证",
    "gerudo_bridge": "成年骑伊波娜跳桥/长钩索过格鲁德断桥",
    "desert_access": "魂之慰灵曲 或 格鲁德会员证",
    "zora_fountain_child": "向卓拉王出示瓶中信",
    "water_medal": "水之奖章",
    "mask_keaton": "奇坦面具",
    "mask_skull": "骷髅面具",
    "mask_truth": "真实面具",
    "lens_truth": "真实眼镜",
    "tokens_10": "10个黄金骷髅蜘蛛的证明",
    "tokens_20": "20个黄金骷髅蜘蛛的证明",
    "tokens_30": "30个黄金骷髅蜘蛛的证明",
    "tokens_40": "40个黄金骷髅蜘蛛的证明",
    "tokens_50": "50个黄金骷髅蜘蛛的证明",
    "note07_password": "成年在树洞外读妖精笔记(暗号「卖点东西呗」)",
    "note12_spider_cleared": "幼年先清掉该地洞墙上普通大蜘蛛",
}

CAP_HOW_TO_GET_ZH = {
    "child": "回到时之神殿，将大师之剑插回台座变回幼年",
    "adult": "集齐3颗精灵石并吹奏时之歌打开时之门，拔出大师之剑成为成年",
    "sword": "幼年在科奇里森林西南迷宫宝箱取得科克里之剑，或成年自带大师之剑",
    "deku_stick": "击倒德库巴巴（食人花）或商店购买即可获得",
    "slingshot": "在德库树长老体内宝箱取得妖精弹弓",
    "boomerang": "在加卜加卜大人腹中宝箱取得回旋镖（仅幼年可用）",
    "bomb": "在多东哥洞窟宝箱取得炸弹袋",
    "hammer": "成年在火之神殿宝箱取得百万吨锤",
    "bow": "成年在森之神殿宝箱取得妖精之弓",
    "hookshot": "成年去墓地拉开有花/可推的墓碑跳下，墓室赛跑胜出丹培获得钩索",
    "longshot": "成年在水之神殿击败中首领黑暗林克后开启宝箱取得长钩索",
    "iron_boots": "成年在卓拉之泉冰之洞窟尽头宝箱取得铁靴",
    "hover_boots": "成年在暗之神殿击败中首领死手后开启宝箱取得浮空靴",
    "goron_bracelet": "幼年在鼓隆城首领房间对达鲁尼亚吹莎莉亚之歌获得鼓隆手环",
    "silver_gauntlets": "幼年从魂之神殿穿过通道出外侧大宝箱取得银护手（成年即可使用）",
    "golden_gauntlets": "成年在加侬多夫城堡内部暗之结界区宝箱取得金护手",
    "bottle": "幼年卡卡利科村抓7只鸡 / 荣蓉牧场找鸡 / 海利亚湖底捞瓶中信 / 成年猎10只大魄",
    "magic": "幼年炸开海拉鲁城堡门旁岩石拜访大妖精获得魔力槽",
    "dins_fire": "炸开死亡之山登山道山顶岩石拜访大妖精学习迪荧之火",
    "fire_arrow": "通关水之神殿后，在海利亚湖畔小岛清晨朝太阳射箭获得火箭",
    "ocarina": "离开科奇里森林桥上由莎莉亚赠送妖精之笛（或海拉鲁城堡护城河捡时之笛）",
    "zelda_lullaby": "幼年潜入海拉鲁城堡花园见塞尔达公主学习塞尔达摇篮曲",
    "lullaby": "幼年潜入海拉鲁城堡花园见塞尔达公主学习塞尔达摇篮曲",
    "epona": "幼年在荣蓉牧场找小玛蓉拿出笛子学习伊波娜之歌",
    "epona_adult": "成年去荣蓉牧场吹伊波娜之歌骑马找印格赛马连赢两场并飞跃牧场围墙",
    "saria": "拿到塞尔达的信后穿过迷途森林到森之圣域找莎莉亚学习莎莉亚之歌",
    "sun_song": "拿到塞尔达摇篮曲后进入墓地最深处王家墓穴，调查石碑学习太阳之歌",
    "song_of_time": "集齐3颗精灵石回海拉鲁城堡护城河边触发事件捡取时之笛并学习时之歌",
    "storm_song": "成年后进入卡卡利科村风车小屋，拿出时之笛对风车大叔吹奏学习岚之歌",
    "minuet": "成年后进入森之圣域前由希克教授森之小步舞曲",
    "bolero": "成年后从鼓隆城达鲁尼亚房间密道或山顶进入死亡之山火山口由希克教授火之波丽露舞曲",
    "serenade": "在卓拉之泉冰之洞窟取得铁靴时由希克教授水之小夜曲",
    "requiem": "成年穿过幻影沙漠到达巨大邪神像门前，进魂之神殿再出来触发希克教授魂之慰灵曲",
    "nocturne": "成年通关森/火/水三大神殿后回到卡卡利科村触发村庄着火剧情由希克教授暗之梦幻曲",
    "scarecrow": "幼年在海利亚湖畔对稻草人吹自定义8音符，成年后再来吹一遍激活稻草人之歌",
    "scarecrow_longshot": "先在水之神殿拿【长钩索】（短钩索够不到屋顶！），并在幼年与成年分别对湖畔稻草人吹自定义8音符激活《稻草人之歌》",
    "zora_tunic": "成年用蓝色火焰解冻卓拉王获赠卓拉服，或在卓拉领地商店300卢比购买",
    "goron_tunic": "成年用炸弹炸停鼓隆城滚动的小鼓隆获赠鼓隆服，或在鼓隆城商店200卢比购买",
    "silver_scale": "幼年在卓拉领地瀑布旁跳水小游戏取得银鳞片",
    "gold_scale": "成年在海利亚湖畔钓鱼池钓到超过60cm（61cm+）大鱼（勿用沉水假饵）赢取金鳞片",
    "magic_bean": "幼年在卓拉河入口找卖豆大叔购买魔法豆（初始10卢比/颗）并种在软土里",
    "bean_lw01": "回幼年形态去卓拉河买魔法豆，种在迷途森林森之舞台草坪软土里，成年后即可乘飞叶上高树",
    "bean_lh": "回幼年形态把魔法豆种在海利亚湖畔实验室旁软土里，成年后即可乘飞叶上去",
    "bean_gy": "回幼年形态把魔法豆种在墓地左侧软土里，成年后即可乘飞叶上高台",
    "bean_dmt": "回幼年形态把魔法豆种在死亡之山多东哥洞窟入口前软土里，成年后乘飞叶上崖顶",
    "bean_dmc": "回幼年形态吹火之波丽露舞曲去死亡之山火山口传送点软土种下魔法豆，成年后乘飞叶上顶",
    "bean_dc": "回幼年形态吹魂之慰灵曲去巨大邪神像门前软土种下魔法豆，成年后乘飞叶上石拱门",
    "zelda_letter": "幼年潜入海拉鲁城堡花园见塞尔达公主获得塞尔达的信",
    "gerudo_card": "过格鲁德断桥进入格鲁德要塞后（未拿证前东侧骑马射箭场与北侧沙漠门均封锁），从牢房窗台用【钩索】翻出，潜入盗贼基地用【妖精之弓】射晕巡逻卫兵，击败4名盗贼首领救出4名木匠获赠【格鲁德会员证】",
    "gerudo_bridge": "成年在荣蓉牧场赛马赢下【伊波娜】后骑马加速飞跃格鲁德之谷断桥（或在水之神殿拿【长钩索】钩过）；过桥即达桥西帐篷木匠头领处（可交【偷猎者的锯子】换【折断的鼓隆之剑】，无需进要塞后方）",
    "desert_access": "先在成年骑伊波娜/用长钩索过格鲁德之谷断桥，在要塞用钩索+妖精之弓救出4名木匠拿【格鲁德会员证】，再穿越幻影沙漠去巨大邪神像学【魂之慰灵曲】",
    "zora_fountain_child": "幼年在海利亚湖底捡【瓶中信】，回卓拉领地装备使用给卓拉王看让他挪开",
    "water_medal": "成年通关水之神殿击败首领【水栖核细胞 摩法】获得水之奖章",
    "mask_keaton": "拿塞尔达的信开启海拉鲁城邑幸福面具店借【奇坦面具】，卖给卡卡利科村北门卫兵",
    "mask_skull": "卖掉奇坦面具后回面具店借【骷髅面具】，卖给迷途森林的骷髅小子",
    "mask_truth": "依次卖完奇坦面具→骷髅面具→诡异面具→兔子兜帽（卖给海拉鲁平原跑步男）后回店借出【真实面具】",
    "lens_truth": "先成年去卡卡利科村风车小屋学【岚之歌】→插剑回幼年→风车小屋吹岚之歌抽干水井→进井底击败死手拿【真实眼镜】（非面具店的真实面具）",
    "tokens_10": "集满10个黄金骷髅蜘蛛的证明后回卡卡利科村蜘蛛屋与解除诅咒的NPC对话领取",
    "tokens_20": "集满20个黄金骷髅蜘蛛的证明后回卡卡利科村蜘蛛屋领奖",
    "tokens_30": "集满30个黄金骷髅蜘蛛的证明后回卡卡利科村蜘蛛屋领奖",
    "tokens_40": "集满40个黄金骷髅蜘蛛的证明后回卡卡利科村蜘蛛屋领奖",
    "tokens_50": "集满50个黄金骷髅蜘蛛的证明后回卡卡利科村蜘蛛屋领奖",
    "note07_password": "成年后前往海拉鲁平原卡卡利科村路口单树洞旁[50.4, 149.4, 18.3]阅读发光妖精笔记，得知暗号「卖点东西呗」再回幼年购买",
    "note12_spider_cleared": "这是Switch2重制版妖精笔记谜题：先插剑回幼年进入此洞（洞口已被炸开可直接跳下），击杀墙上那只普通大蜘蛛；再变回成年回来，洞里后方就会刷出木箱，砸碎木箱即出黄金骷髅蜘蛛！",
}


@dataclass
class EvaluatedItem:
    id: str
    kind: str  # skulltula | heart_piece | quest
    location: str
    name: str
    era: str
    night_only: bool
    collected: bool
    reachable: bool
    missing_reqs: list[str] = field(default_factory=list)
    missing_guides: list[str] = field(default_factory=list)
    guide: str = ""
    floor: str = ""


BOSS_AND_MECHANIC_TIPS: dict[str, list[tuple[str, str]]] = {
    "InsideTheDekuTree": [
        ("大厅蛛网机关", "2楼/3楼从高处助跑纵身跳下，利用重力砸穿1楼中央大蛛网；地下层需点着德库木棒烧掉挡路蛛网，或用木棒引燃未点亮的火把。"),
        ("三只德库坚果暗门顺序", "见到挡门的德库三兄弟按「2 → 3 → 1」的顺序用德库盾反弹它们的坚果即可打败并开门。"),
        ("首领 · 寄生装甲蛛甲兽 哥玛", "等它爬上天花板或眼睛变红瞬间，用【妖精弹弓】（或德库坚果）射中红眼将其击落，立刻上前跳劈/连斩；它产卵时顺手清掉小怪。"),
    ],
    "DodongoCavern": [
        ("巨型骷髅眼睛红光机关（隐藏门）", "在大厅二楼吊桥上，往下方巨型骷髅【左右两只眼洞各扔一颗炸弹】！两只眼睛都炸亮变红后，骷髅大嘴张开即可进入首领区域。"),
        ("楼梯降落机关", "在一楼东侧炸弹花柱旁放炸弹炸塌大石柱，就能形成通往二楼的大楼梯。"),
        ("首领 · 猛炎古代龙 多东哥王", "等它张大嘴深吸气准备喷火时，立刻把炸弹（或炸弹花）扔进它嘴里！炸晕倒地后用剑砍击；它卷成球滚来时贴着熔岩边缘举海利亚盾防御。"),
    ],
    "ZoraDomain": [
        ("卓拉王挪位机关", "从海利亚湖底捡到【瓶中信】后装备在快捷栏，站到王座前对卓拉王使用瓶中信，他就会慢慢挪开让出通往卓拉之泉的路。"),
        ("王座取火点亮瀑布火把", "用德库木棒从王座旁的火盆引火，依次跑去点亮下方地面与瀑布后的火把，瀑布下方会出现心之碎片宝箱。"),
    ],
    "ZoraFountain": [
        ("进入加卜加卜大人体内", "先在卓拉领地浅水或海利亚湖畔用空瓶抓一条鱼，站到加卜加卜大人嘴巴正前方放出鱼，他张嘴时即可被吞入腹中。"),
        ("大妖精【法露尔之风】", "游到卓拉之泉右下角（东南侧，大树对岸）小岛，用炸弹炸开石壁裂缝进入泉水吹【塞尔达摇篮曲】。"),
    ],
    "InsideJabuJabuBelly": [
        ("露托公主机关", "见到露托公主后落洞，带她压住蓝色机关开关（抱起放在开关上，或按她指示搬运）；拿到回旋镖后先去清理寄生触手。"),
        ("中首领 · 大章鱼", "先用 Z 锁定，等它旋转背对你露出绿色弱点时用【回旋镖】定身，再上前用剑输出（不要硬刚正面）。"),
        ("首领 · 电击旋回虫 啪哩内德", "第一阶段用【回旋镖】切断连在天花板上的 3 根触手；第二阶段用回旋镖打散外围水母再击晕本体电球，趁机近身连斩。"),
    ],
    "ForestTemple": [
        ("4只幽灵姐妹与扭曲走廊", "前两只幽灵在画廊墙画里，拉远距离用妖精之弓射（靠近画就会躲）；绿/蓝幽灵需在时限内推拼图箱拼出完整图案，最后击败大姐梅格。"),
        ("首领 · 来自异次元的恶灵 幻影加侬", "第一阶段观察周围画框，用妖精之弓射向真马冲出来的那幅画（假马会折返）；第二阶段用大师之剑把他的光球打回去对弹，击晕落地后连砍。"),
    ],
    "FireTemple": [
        ("解救鼓隆族拿钥匙", "每层都有牢房关着鼓隆族，留意假墙（用炸弹炸开）和从顶层砸落开关。"),
        ("中首领 · 火舞者", "等它跑圈时用【钩索】直接拉出中心黑色本体（或在它跑向你时提前放炸弹），本体脱离火衣后立刻追砍。"),
        ("首领 · 灼热穴居龙 瓦尔基亚", "它从熔岩洞冒出头时用【百万吨锤】猛敲头部敲晕后连击；它飞天吐落石时躲到边缘或挂在平台边上。"),
    ],
    "IceCavern": [
        ("蓝火融化红冰", "先用空瓶装上蓝色火焰（可反复取），所有拦路的红色坚冰都要靠倒蓝火融化；拿到【铁靴】后希克会教你【水之小夜曲】。"),
    ],
    "WaterTemple": [
        ("3个水位开关（防卡关必看）", "底层最右墙吹【塞尔达摇篮曲】降到最低水→回中层中央塔内吹曲升至半水→顶层大厅墙面吹曲升至最高水；升到半水时记得潜进中央塔浮起的木块下方暗洞拿隐藏小钥匙！"),
        ("中首领 · 黑暗林克", "不要用 Z 锁定（否则他会同步防反你）！直接用【大鼓隆之剑】、【迪荧之火】或【百万吨锤】无锁定强攻即可速胜，前方宝箱拿【长钩索】。"),
        ("首领 · 水栖核细胞 摩法", "站在四角平台上躲开触手抓人，用【长钩索】把水柱里的红色核心拉出水面再近身连续挥砍。"),
    ],
    "BottomOfTheWell": [
        ("放水与真实眼镜", "进井后先走到对面房间吹【塞尔达摇篮曲】放干水，退回入口跳入地下通道；留意到处都是假墙与隐藏陷阱。"),
        ("中首领 · 死手", "故意靠近白色长手被抓住触发主体钻出，快速按键挣脱后趁它低头咬人时疯狂斩击头部，击败后开宝箱拿【真实眼镜】。"),
    ],
    "ShadowTemple": [
        ("真实眼镜常备", "本神殿大量隐形平台、假墙、假地刺与隐形刀刃，过图全程按需开启【真实眼镜】；鬼船区域末端需在过桥/上岸前用妖精之弓射对岸炸弹花炸倒石柱搭桥。"),
        ("首领 · 暗影魔幻兽 邦戈邦戈", "穿【浮空靴】（或看鼓面节奏）开【真实眼镜】，先用妖精之弓射晕它的两只巨手，再趁本体大红眼冲过来时用弓射眼击晕砍击。"),
    ],
    "SpiritTemple": [
        ("幼年/成年双线攻略", "幼年先穿过幻影沙漠进左侧小洞帮娜波露拿【银护手】；再切回成年用银护手推开大厅巨石继续推进，用【镜盾】反射阳光开启太阳机关。"),
        ("中首领 · 铁甲武士", "先引诱它挥斧重砸顺便让它帮你劈碎房间柱子（掉心），躲开重砸后跳劈破甲，破甲后注意它会加速。"),
        ("首领 · 双生魔导师 双子妖婆", "第一阶段站在柱子上用【镜盾】把火魔女的光束反射给冰魔女（反之亦然）；第二阶段合体后用镜盾连续吸收【同一种属性魔法3次】再释放反击激光晕倒斩杀。"),
    ],
    "InsideGanonCastle": [
        ("六贤者结界破解", "一楼四周共有6间对应各属性奖章的小关卡，逐个击破结界水晶后中央光柱消失即可登塔；别忘了塔外废墟巨石后的防御力加倍大妖精。"),
    ],
    "GanonCastle": [
        ("最终战 · 大魔王 加侬多夫 & 加侬", "第一阶段和加侬多夫互打光球并用【光箭】射晕再飞去砍；变身加侬初期没有大师之剑，用【百万吨锤/大鼓隆之剑/德库坚果】穿裆绕背打尾巴，取回大师之剑后用光箭射晕再终结。"),
    ],
}


BIGGORON_CHAIN_STEPS: dict[int, tuple[str, str, str, str, bool]] = {
    0xD157B76F: ("1/11", "KakarikoVillage", "找卡卡利科村鸡圈红发鸡姐姐拿【口袋蛋】", "在鸡圈旁对话红发鸡姐姐领取【口袋蛋】。", False),
    0x777EA18C: ("1/11", "KakarikoVillage", "等待【口袋蛋】孵化（吹太阳之歌或等天亮）", "吹奏两次【太阳之歌】即可让口袋蛋立刻孵出【闹铃鸡】。", False),
    0x3E6C49BC: ("2/11", "KakarikoVillage", "带着孵出的【闹铃鸡】去叫醒塔隆", "去卡卡利科村西北小屋对着睡觉的塔隆使用【闹铃鸡】叫醒他。", False),
    0xEB62ADD9: ("2/11", "KakarikoVillage", "带着孵出的【闹铃鸡】去叫醒塔隆", "去卡卡利科村西北小屋对着睡觉的塔隆使用【闹铃鸡】叫醒他。", False),
    0x93E1D7D7: ("2/11", "KakarikoVillage", "带着孵出的【闹铃鸡】去叫醒塔隆", "去卡卡利科村西北小屋对着睡觉的塔隆使用【闹铃鸡】叫醒他。", False),
    0x0E5AFAD8: ("3/11", "KakarikoVillage", "回【卡卡利科村】鸡圈把闹铃鸡还给红发鸡姐姐", "找鸡圈旁红发鸡姐姐归还闹铃鸡，获赠蓝色小鸡【克吉罗】。", False),
    0x6F917DFE: ("4/11", "LostWood", "去【迷途森林】把【克吉罗】交给木匠儿子", "科奇里森林进直接向【左】走；若从鼓隆城捷径进：出洞直走→下一间右转→直走穿过入口间，对树桩上的瞌睡哥使用【克吉罗】换【奇异蘑菇】（拿到后开始限时！）。", False),
    0x14376953: ("4/11", "LostWood", "去【迷途森林】把【克吉罗】交给木匠儿子", "科奇里进向【左】走；鼓隆城捷径进则直走→右转→直走穿过入口间，对树桩上的瞌睡哥使用【克吉罗】换【奇异蘑菇】。", False),
    0xD932A31C: ("4/11", "LostWood", "去【迷途森林】把【克吉罗】交给木匠儿子", "科奇里进向【左】走；鼓隆城捷径进则直走→右转→直走穿过入口间，对树桩上的瞌睡哥使用【克吉罗】换【奇异蘑菇】。", False),
    0x057EF5F8: ("4/11", "LostWood", "奇异蘑菇已过期！回【迷途森林】找瞌睡哥重拿【奇异蘑菇】", "去迷途森林树桩处重新找瞌睡哥领取【奇异蘑菇】（科奇里进向左 / 鼓隆城进直走→右转→直走；拿后直接跑/骑马去卡卡利科村）。", False),
    0x27F660FE: ("5/11", "KakarikoVillage", "⏳限时！带【奇异蘑菇】立刻去【卡卡利科村】老奶奶药店", "千万别用传送曲/太阳之歌！回卡卡利科村从正面药铺旁门进高台或后门上梯进老奶奶药铺交付换【奇异药】。", True),
    0x5CDE171F: ("6/11", "LostWood", "把【奇异药】带回【迷途森林】交给金发少女法德", "再去迷途森林树桩处找法德（科奇里进向左 / 鼓隆城捷径进直走→右转→直走穿过入口间），交付奇异药获【偷猎者的锯子】。", False),
    0xEC4C4A24: ("6/11", "LostWood", "把【奇异药】带回【迷途森林】交给金发少女法德", "再去迷途森林树桩处找法德（科奇里进向左 / 鼓隆城捷径进直走→右转→直走穿过入口间），交付奇异药获【偷猎者的锯子】。", False),
    0x21D6FA38: ("7/11", "GerudoValley", "把【偷猎者的锯子】送到【格鲁德之谷】交给木匠头领", "骑伊波娜加速跳过格鲁德之谷断桥（或长钩索钩过），在断桥西侧帐篷外直接交给木匠头领换取【折断的鼓隆之剑】（无需进入后方的格鲁德要塞！）。", False),
    0xD7A3DEFB: ("7/11", "GerudoValley", "把【偷猎者的锯子】送到【格鲁德之谷】交给木匠头领", "骑伊波娜跳过格鲁德之谷断桥，在断桥西侧帐篷外直接把锯子交给木匠头领换取【折断的鼓隆之剑】（无需进格鲁德要塞）。", False),
    0x6EF85D0F: ("7/11", "GerudoValley", "把【偷猎者的锯子】送到【格鲁德之谷】交给木匠头领", "骑伊波娜跳过格鲁德之谷断桥，在断桥西侧帐篷外直接把锯子交给木匠头领换取【折断的鼓隆之剑】（无需进格鲁德要塞）。", False),
    0x03C56929: ("7/11", "GerudoValley", "把【偷猎者的锯子】送到【格鲁德之谷】交给木匠头领", "骑伊波娜跳过格鲁德之谷断桥，在断桥西侧帐篷外直接把锯子交给木匠头领换取【折断的鼓隆之剑】（无需进格鲁德要塞）。", False),
    0xEE867C27: ("8/11", "DeathMountainTrail", "把【折断的鼓隆之剑】送到【死亡之山山顶】交给大鼓隆", "爬死亡之山登山道到火山口入口旁见大鼓隆，交付折断的鼓隆之剑换取【处方笺】。", False),
    0xA594ED54: ("9/11", "ZoraDomain", "把【处方笺】带到【卓拉领地】交给卓拉王", "用蓝火解冻卓拉王后把【处方笺】给他看，换取【眼球蛙】（拿到后开始限时！）。", False),
    0xD677164B: ("9/11", "ZoraDomain", "眼球蛙已超时！回【卓拉领地】找卓拉王重领【眼球蛙】", "回到卓拉领地找卓拉王重新领取【眼球蛙】。", False),
    0x5DAECA58: ("10/11", "LakeHylia", "⏳限时！带【眼球蛙】立刻赶去【海利亚湖畔】找博士", "千万别用传送曲/太阳之歌！冲出卓拉领地顺河跑或骑伊波娜直奔海利亚湖畔实验室交给博士换【特制眼药水】。", True),
    0xD2F8ADD5: ("10/11", "LakeHylia", "特制眼药水已过期！回【海利亚湖畔】实验室找博士重领", "进海利亚湖畔实验室重新向博士领取【特制眼药水】。", False),
    0x0BE69809: ("11/11", "DeathMountainTrail", "⏳限时！带【特制眼药水】立刻冲向【死亡之山山顶】交给大鼓隆", "千万别吹传送曲/太阳之歌！直接骑伊波娜奔向卡卡利科村一路爬上山顶把特制眼药水交给大鼓隆，换【兑换券】。", True),
    0x02428C32: ("11/11", "DeathMountainTrail", "拿到【兑换券】！连吹 3 天【太阳之歌】找大鼓隆领剑", "在原地反复吹【太阳之歌】度过 3 天后与大鼓隆对话，即可领取最强双手剑【大鼓隆之剑】！", False),
}

MASK_CHAIN_STEPS: dict[int, tuple[str, str, str, str]] = {
    0x60C72303: ("1/4", "Market", "去【海拉鲁城邑】幸福面具店借【奇坦面具】", "进城邑东北小巷幸福面具店借出【奇坦面具】。"),
    0x08AFCA92: ("1/4", "KakarikoVillage", "戴【奇坦面具】去【卡卡利科村】北门卖给卫兵", "装备奇坦面具和死亡之山入口前卫兵对话卖出（15卢比）。"),
    0xEB62ADD9: ("1/4", "KakarikoVillage", "戴【奇坦面具】去【卡卡利科村】北门卖给卫兵", "装备奇坦面具和死亡之山入口前卫兵对话卖出（15卢比）。"),
    0x0E5AFAD8: ("1/4", "Market", "回【海拉鲁城邑】幸福面具店交还奇坦面具货款", "回到幸福面具店把10卢比交给面具商人并借下一张面具。"),
    0x129D5E69: ("2/4", "Market", "去幸福面具店借【骷髅面具】", "在幸福面具店借出【骷髅面具】。"),
    0x99929480: ("2/4", "LostWood", "戴【骷髅面具】去【迷途森林】卖给骷髅小子", "科奇里进直接向【左】走（若从鼓隆城进：直走→右转→直走穿过入口间），站高树桩前戴骷髅面具对话卖出。"),
    0x6F917DFE: ("2/4", "LostWood", "戴【骷髅面具】去【迷途森林】卖给骷髅小子", "科奇里进直接向【左】走（若从鼓隆城进：直走→右转→直走穿过入口间），戴骷髅面具与骷髅小子对话卖出。"),
    0x27F660FE: ("2/4", "Market", "回【海拉鲁城邑】幸福面具店交还骷髅面具货款", "回幸福面具店付清货款并借下一张【诡异面具】。"),
    0xB2F4850C: ("3/4", "Market", "去幸福面具店借【诡异面具】", "在幸福面具店借出【诡异面具】。"),
    0x0B956482: ("3/4", "Graveyard", "戴【诡异面具】白天去【墓地】卖给小男孩", "白天进卡卡利科村墓地，戴诡异面具和徘徊的小男孩对话卖出。"),
    0x5CDE171F: ("3/4", "Graveyard", "戴【诡异面具】白天去【墓地】卖给小男孩", "白天进卡卡利科村墓地，戴诡异面具和徘徊的小男孩对话卖出。"),
    0x21D6FA38: ("3/4", "Market", "回【海拉鲁城邑】幸福面具店交还诡异面具货款", "回幸福面具店付清货款并借出【兔子兜帽】。"),
    0x57867810: ("4/4", "Market", "去幸福面具店借【兔子兜帽】", "在幸福面具店借出【兔子兜帽】（需集齐3颗精灵石后牧场跑步男才会刷出）。"),
    0x93FAC001: ("4/4", "HyruleField", "戴【兔子兜帽】去【海拉鲁平原】卖给跑步男", "等夜晚他在牧场外跑停坐下后（需3颗精灵石），戴兔子兜帽对话卖出得满钱包。"),
    0xEE867C27: ("4/4", "HyruleField", "戴【兔子兜帽】去【海拉鲁平原】卖给跑步男", "等夜晚他在牧场外跑停坐下后，戴兔子兜帽对话卖出。"),
    0xA594ED54: ("4/4", "Market", "回【海拉鲁城邑】幸福面具店交款领【真实面具】", "回幸福面具店结账，解锁【真实面具】以及鼓隆面具、卓拉面具、格鲁德面具！"),
}


BIGGORON_FULL_ROADMAP = (
    "①卡卡利科村鸡姐姐拿【口袋蛋】 → ②孵出【闹铃鸡】叫醒村里小屋塔隆 → ③交回鸡姐姐换【克吉罗】 → "
    "④迷途森林左转给瞌睡哥换【奇异蘑菇】 → ⑤⏳限时送卡卡利科村老奶奶药店换【奇异药】 → "
    "⑥回迷途森林左转给法德换【偷猎者的锯子】 → ⑦骑伊波娜跳格鲁德之谷断桥给桥西帐篷木匠头领换【折断的鼓隆之剑】 → ⑧登山顶大鼓隆拿【处方笺】 → "
    "⑨卓拉领地给卓拉王换【眼球蛙】 → ⑩⏳限时送海利亚湖畔博士做【特制眼药水】 → ⑪⏳限时送回山顶大鼓隆拿【兑换券】，连吹3天太阳之歌领【大鼓隆之剑】。"
)
MASK_FULL_ROADMAP = (
    "①借【奇坦面具】→卖卡卡利科村北门卫兵 → ②借【骷髅面具】→卖迷途森林左转骷髅小子 → "
    "③借【诡异面具】→白天卖墓地小男孩 → ④借【兔子兜帽】→集齐3颗精灵石后夜卖海拉鲁平原跑步男 → 回城邑幸福面具店领【真实面具】。"
)


def get_lostwood_room_guidance(player_pos: tuple[float, float, float] | None, target: str = "fado") -> str | None:
    """Return room-accurate LostWood turn directions based on live player (x, z)."""
    if not player_pos:
        return None
    px, _py, pz = player_pos
    if 12.0 <= px <= 36.0 and -36.0 <= pz <= -12.0:
        # Room (24, -24): Goron City shortcut room
        if target == "sfm":
            return "【你当前在鼓隆城捷径路口】面向南(进林)：左转(东) → 下间左转(北) → 直走 → 左转 → 右转即达【森之圣域】"
        return "【你当前在鼓隆城捷径路口】面向南直走过门 → 下间右转(西) → 直走穿过入口间即到树桩（注意别走正西侧死路）"
    if 36.0 < px <= 75.0 and -36.0 <= pz <= -12.0:
        # Room (48, -24): Zora River shortcut room
        if target == "sfm":
            return "【你当前在卓拉河捷径房间】上岸向北右转 → 直走(北) → 左转(西) → 右转(北)即达【森之圣域】"
        return "【你当前在卓拉河捷径房间】上岸向西直走 → 下间左转(南) → 下间右转(西) → 直走穿过入口间即到树桩"
    if 12.0 <= px <= 36.0 and -12.0 < pz <= 14.0:
        # Room (24, 0)
        if target == "sfm":
            return "【迷途森林第2间】向北直走 → 右转(东) → 左转(北) → 直走 → 左转 → 右转即达【森之圣域】"
        return "【迷途森林第2间】向西(往科奇里方向)退回入口间，再直走穿过即到树桩！"
    if -12.0 <= px <= 12.0 and -12.0 <= pz <= 14.0:
        # Room (0, 0): Kokiri Forest entrance
        if target == "sfm":
            return "【科奇里入口间】按【右 → 左 → 右 → 左 → 直走 → 左 → 右】即达【森之圣域】"
        return "【科奇里入口间】直接向【左(西)】进门即到树桩！"
    if px < -12.0:
        return "【你已进入西侧树桩/木桥区】直接靠近树桩或沿路往南即可！"
    if 36.0 < px <= 62.0 and -60.0 <= pz < -36.0:
        if target == "sfm":
            return "【前往圣域中段】往北直走 → 左转(西) → 右转(北)即达【森之圣域】"
        return "【前往圣域中段】向南退两间到路口右转(西)，再左转(南)→右转(西)→直走回树桩"
    return None


def _format_3d_radar(dx: float, dy: float, dz: float, is_adj_room: bool = False) -> tuple[str, str, str]:
    """Compute minimap 8-way compass direction + vertical elevation camera pitch hint."""
    import math
    d_xz = (dx * dx + dz * dz) ** 0.5
    if d_xz < 1.8:
        compass = "正上方/正脚下🧭"
    else:
        deg = math.degrees(math.atan2(-dz, dx))  # 0=East(+X), 90=North(-Z), 180=West(-X), -90=South(+Z)
        if -22.5 <= deg < 22.5:
            compass = "小地图【东➡️】"
        elif 22.5 <= deg < 67.5:
            compass = "小地图【东北↗】"
        elif 67.5 <= deg < 112.5:
            compass = "小地图【北⬆️】"
        elif 112.5 <= deg < 157.5:
            compass = "小地图【西北↖】"
        elif deg >= 157.5 or deg < -157.5:
            compass = "小地图【西⬅️】"
        elif -157.5 <= deg < -112.5:
            compass = "小地图【西南↙】"
        elif -112.5 <= deg < -67.5:
            compass = "小地图【南⬇️】"
        else:
            compass = "小地图【东南↘】"

    if dy >= 6.5:
        elev = f"⬆️极高天花板/上层(+{dy:.1f}m·第一人称大仰角抬头看顶!)"
    elif dy >= 2.4:
        elev = f"⬆️头顶高墙/天花板(+{dy:.1f}m·开第一人称抬头看!)"
    elif dy <= -3.0:
        elev = f"⬇️脚下低处/下层({dy:.1f}m·低头往断崖/坑底看!)"
    else:
        elev = f"↔同层高度({dy:+.1f}m·平视四周墙/柱后)"

    prefix = "【邻室/隔栏】" if is_adj_room else ""
    return compass, elev, f"{prefix}{compass} · {elev}"


def compute_nearby_hints(
    curr_loc: str,
    player_pos: tuple[float, float, float] | None,
    all_items: list[EvaluatedItem],
    db: dict[str, Any],
    dungeon_room: int | None = None,
) -> list[dict[str, Any]]:
    """Find uncollected Gold Skulltulas (and the 3 AgonyStone Skulltula grottos) & nearby Heart Pieces.
    Note: In Switch 2 OoT Remake, regular HidingHoles do NOT trigger the Stone of Agony badge."""
    if not player_pos:
        return []
    px, py, pz = player_pos
    by_id = {it.id: it for it in all_items}
    raw_pos_by_id: dict[str, list[float]] = {}
    raw_room_by_id: dict[str, int] = {}
    for raw in db.get("skulltulas", []) + db.get("heart_pieces", []):
        if "pos" in raw:
            raw_pos_by_id[raw["id"]] = raw["pos"]
        if "room" in raw:
            raw_room_by_id[raw["id"]] = int(raw["room"])

    hints: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()

    # 1. Only check AgonyStone-linked grottos (the 3 hidden grottos containing uncollected Skulltulas)
    for g in db.get("grottos", []):
        if g.get("loc") != curr_loc or not g.get("is_agony"):
            continue
        gx, gy, gz = g["pos"]
        dx, dy, dz = gx - px, gy - py, gz - pz
        d_xz = (dx * dx + dz * dz) ** 0.5
        if d_xz <= 30.0 and abs(dy) <= 22.0:
            compass, elev, radar = _format_3d_radar(dx, dy, dz, False)
            uncol = [by_id[iid] for iid in g.get("item_ids", []) if iid in by_id and not by_id[iid].collected and iid.startswith("gs_")]
            for it in uncol:
                seen_item_ids.add(it.id)
                hints.append({
                    "key": f"grotto_item:{it.id}",
                    "kind": it.kind,
                    "dist": round(d_xz, 1),
                    "dy": round(dy, 1),
                    "compass": compass,
                    "elev": elev,
                    "radar": radar,
                    "name": f"附近隐藏地洞内 · {it.name}",
                    "reachable": it.reachable,
                    "missing_reqs": list(it.missing_reqs),
                    "guide": it.guide or (it.missing_guides[0] if (not it.reachable and it.missing_guides) else ""),
                    "night_only": it.night_only,
                    "floor": it.floor,
                    "is_grotto": True,
                })

    # 2. Check uncollected Gold Skulltulas (<= 28m in same room, or <= 15m across adjacent same-floor doorway/grate) and Heart Pieces (<= 18m)
    for it in all_items:
        if it.location != curr_loc or it.collected or it.id in seen_item_ids:
            continue
        ipos = raw_pos_by_id.get(it.id)
        if not ipos:
            continue
        ix, iy, iz = ipos
        dx, dy, dz = ix - px, iy - py, iz - pz
        d_xz = (dx * dx + dz * dz) ** 0.5
        sk_room = raw_room_by_id.get(it.id)
        is_adj_room = False
        if dungeon_room is not None and sk_room is not None and dungeon_room != sk_room:
            if d_xz <= 15.0 and abs(dy) <= 7.5:
                is_adj_room = True
            else:
                continue
        max_r = 28.0 if it.kind == "skulltula" else 18.0
        max_dy = 26.0 if it.kind == "skulltula" else 18.0
        if d_xz <= max_r and abs(dy) <= max_dy:
            compass, elev, radar = _format_3d_radar(dx, dy, dz, is_adj_room)
            hints.append({
                "key": f"item:{it.id}",
                "kind": it.kind,
                "dist": round(d_xz, 1),
                "dy": round(dy, 1),
                "compass": compass,
                "elev": elev,
                "radar": radar,
                "name": it.name,
                "reachable": it.reachable,
                "missing_reqs": list(it.missing_reqs),
                "guide": it.guide or (it.missing_guides[0] if (not it.reachable and it.missing_guides) else ""),
                "night_only": it.night_only,
                "floor": it.floor,
                "is_grotto": False,
            })

    hints.sort(key=lambda h: (0 if h["kind"] == "skulltula" else 1, h["dist"]))
    return hints


def compute_active_chains(caps: dict[str, Any], kv: dict[int, int], cap_hashes: dict[str, int], curr_loc: str, loc_names: dict[str, str], player_pos: tuple[float, float, float] | None = None) -> list[dict[str, Any]]:
    """Return active multi-step trading/chain quests that should stay persistently pinned across regions."""
    chains: list[dict[str, Any]] = []

    # 1. Biggoron's Sword 11-step trading chain (Adult Link)
    h_bg_got = cap_hashes.get("IsGet.Weapon_Sword_Biggoron")
    if not caps["is_child"] and not (h_bg_got and kv.get(h_bg_got, 0)):
        h_bg_enum = cap_hashes.get("Biggoron_State_Enum")
        bg_val = kv.get(h_bg_enum, 0) if h_bg_enum else 0
        info = BIGGORON_CHAIN_STEPS.get(bg_val)
        if not info:
            # Fallback to Booleans if Enum wasn't captured
            h_cucco = cap_hashes.get("GetSwordBigGoron_IsAfterFirstShowCucco_Npc_Hylia_049_Adult")
            h_talk = cap_hashes.get("GetSwordBigGoron_IsAfterFirstTalk_Npc_Hylia_049_Adult")
            if h_cucco and kv.get(h_cucco, 0):
                bg_val = 0x6F917DFE
                info = BIGGORON_CHAIN_STEPS[bg_val]
            elif h_talk and kv.get(h_talk, 0):
                bg_val = 0x777EA18C
                info = BIGGORON_CHAIN_STEPS[bg_val]
        if info:
            step_num, tloc, title, detail, timed = info
            if curr_loc == "LostWood" and tloc == "LostWood":
                rg = get_lostwood_room_guidance(player_pos, target="fado")
                if rg:
                    detail = rg
            tloc_zh = loc_names.get(tloc, tloc)
            chains.append({
                "id": "chain_biggoron",
                "step_key": hex(bg_val),
                "badge": "⏳" if timed else "🗡",
                "header": f"{'⏳限时！' if timed else ''}大鼓隆之剑支线 {step_num}",
                "title": title,
                "target_loc": tloc,
                "target_zh": tloc_zh,
                "in_target": (curr_loc == tloc),
                "timed": timed,
                "detail": detail,
                "roadmap": BIGGORON_FULL_ROADMAP,
            })

    # 2. Happy Mask Shop 4-mask trading chain (Child Link)
    if caps["is_child"] and not caps.get("mask_truth"):
        h_mk_enum = cap_hashes.get("MaskSalesman_State_Enum")
        mk_val = kv.get(h_mk_enum, 0) if h_mk_enum else 0
        minfo = MASK_CHAIN_STEPS.get(mk_val)
        if minfo:
            step_num, tloc, title, detail = minfo
            if curr_loc == "LostWood" and tloc == "LostWood":
                rg = get_lostwood_room_guidance(player_pos, target="fado")
                if rg:
                    detail = rg
            tloc_zh = loc_names.get(tloc, tloc)
            chains.append({
                "id": "chain_masks",
                "step_key": hex(mk_val),
                "badge": "🎭",
                "header": f"幸福面具店支线 {step_num}",
                "title": title,
                "target_loc": tloc,
                "target_zh": tloc_zh,
                "in_target": (curr_loc == tloc),
                "timed": False,
                "detail": detail,
                "roadmap": MASK_FULL_ROADMAP,
            })

    return chains


def compute_story_tracker(caps: dict[str, Any], kv: dict[int, int], cap_hashes: dict[str, int], curr_loc: str) -> dict[str, Any]:
    """Derive exact live Main Story objective, destination, and next steps from save flags."""
    def _hb(k: str) -> bool:
        h = cap_hashes.get(k)
        return bool(kv.get(h, 0)) if h else False

    has_deku_stone = _hb("IsGet.Item_Stone_Forest")
    has_fire_stone = _hb("IsGet.Item_Stone_Fire")
    has_water_stone = _hb("IsGet.Item_Stone_Water")
    has_letter = _hb("IsGet.Item_ZeldaLetter")
    has_ruto_bottle = _hb("IsGet.Item_Bottle_Letter")
    zora_fountain_open = _hb("HavePlayedEvent.Dm_ZoraFountain_0000")
    has_master_sword = _hb("IsGet.Weapon_Sword_Master")
    has_forest_m = _hb("IsGet.Item_Medal_Forest")
    has_fire_m = _hb("IsGet.Item_Medal_Fire")
    has_water_m = _hb("IsGet.Item_Medal_Water")
    has_shadow_m = _hb("IsGet.Item_Medal_Shadow")
    has_spirit_m = _hb("IsGet.Item_Medal_Spirit")
    has_light_arrow = _hb("IsGet.Item_Arrow_Light")

    if not caps["sword"] and not has_deku_stone:
        cur = {
            "stage": "序章 · 科奇里森林",
            "title": "取得【科克里之剑】与【德库盾】，拜访德库树长老",
            "target_loc": "KokiriForest",
            "target_zh": "科奇里森林 → 德库树长老体内",
            "how_to": "去森林西南迷宫拿【科克里之剑】、攒40卢比在商店买【德库盾】，装备后向东找拦路的米德即可进入德库树长老体内。",
        }
    elif not has_deku_stone:
        cur = {
            "stage": "主线 1/3 · 科克里翡翠",
            "title": "攻略【德库树长老体内】取得【科克里翡翠】",
            "target_loc": "InsideTheDekuTree",
            "target_zh": "德库树长老体内",
            "how_to": "拿2楼宝箱的【妖精弹弓】，从高处跳下砸穿1楼中央蛛网进入地下，按「2→3→1」击败德库三兄弟后打败首领【寄生装甲蛛甲兽 哥玛】（弹弓射红眼）。",
        }
    elif not has_letter:
        cur = {
            "stage": "主线 · 拜访塞尔达公主",
            "title": "前往【海拉鲁城堡】见塞尔达学曲并拿信",
            "target_loc": "HyruleCastle",
            "target_zh": "海拉鲁城邑 → 海拉鲁城堡",
            "how_to": "穿海拉鲁平原北上进城邑，门前找玛蓉拿【奇怪的蛋】（或等天亮孵出【孵小鸡】叫醒塔隆翻藤蔓+游泳潜入城堡花园），与塞尔达对话学【塞尔达摇篮曲】并得【塞尔达的信】。记得在城堡外炸石拜访大妖精学【迪荧之火】/魔力槽！",
        }
    elif not caps["goron_bracelet"]:
        cur = {
            "stage": "主线 · 解锁鼓隆手环",
            "title": "去【森之圣域】学【莎莉亚之歌】，再去【鼓隆城】找达鲁尼亚",
            "target_loc": "SacredForestMeadow" if not caps["saria"] else "GoronCity",
            "target_zh": "森之圣域 → 卡卡利科村 → 鼓隆城",
            "how_to": (
                "若还没学【莎莉亚之歌】，先去科奇里森林进迷途森林按「右→左→右→左→直走→左→右」见莎莉亚；然后去卡卡利科村北门卫兵出示【塞尔达的信】上死亡之山，进鼓隆城底层大门前吹【塞尔达摇篮曲】并给达鲁尼亚吹【莎莉亚之歌】获【鼓隆手环】。"
            ),
        }
    elif not has_fire_stone:
        cur = {
            "stage": "主线 2/3 · 鼓隆红宝石",
            "title": "攻略【多东哥洞窟】拿【炸弹袋】并取得【鼓隆红宝石】",
            "target_loc": "DodongoCavern",
            "target_zh": "死亡之山登山道 → 多东哥洞窟",
            "how_to": "出鼓隆城用【鼓隆手环】抱起台阶边炸弹花扔下崖壁炸开洞口进入多东哥洞窟。拿【炸弹袋】后在二楼吊桥往大骷髅两只眼睛各扔一颗炸弹（两眼变红张嘴），打败首领【猛炎古代龙 多东哥王】（吸气时往嘴里扔炸弹）。",
        }
    elif not caps["silver_scale"]:
        cur = {
            "stage": "主线 3/3 · 卓拉蓝宝石（1/3）",
            "title": "前往【卓拉领地】跳水拿【银鳞片】",
            "target_loc": "ZoraDomain",
            "target_zh": "海拉鲁平原东侧 → 卓拉河 → 卓拉领地",
            "how_to": "从平原东北方进入卓拉河逆流而上，在尽头大瀑布前纹章上吹【塞尔达摇篮曲】进入卓拉领地；从王座左上方走出瀑布悬崖找跳水卓拉玩20卢比跳水小游戏获得【银鳞片】。",
        }
    elif not has_ruto_bottle:
        cur = {
            "stage": "主线 3/3 · 卓拉蓝宝石（2/3）",
            "title": "去【海利亚湖畔】水底捡取露托公主的【瓶中信】",
            "target_loc": "LakeHylia",
            "target_zh": "卓拉领地捷径 / 海拉鲁平原南侧 → 海利亚湖畔",
            "how_to": "拿到【银鳞片】后从卓拉领地水底捷径（或步行去海利亚湖畔），潜入湖底北岸捡起闪烁的【瓶中信】。",
        }
    elif not has_water_stone:
        if not zora_fountain_open:
            cur = {
                "stage": "主线 3/3 · 卓拉蓝宝石（3/3）",
                "title": "回【卓拉领地】给卓拉王出示【瓶中信】，进卓拉之泉＆加卜加卜大人",
                "target_loc": "ZoraDomain",
                "target_zh": "卓拉领地 → 卓拉之泉 → 加卜加卜大人腹中",
                "how_to": "回到卓拉领地王座前，把【瓶中信】装备到快捷栏并使用给卓拉王看，让他挪开进入卓拉之泉！进入后：1）先用空瓶抓一条鱼放在加卜加卜大人面前进入迷宫；2）顺道去右下角小岛炸墙拜访大妖精学【法露尔之风】！",
            }
        else:
            cur = {
                "stage": "主线 3/3 · 卓拉蓝宝石（最终步）",
                "title": "攻略【加卜加卜大人腹中】取得【卓拉蓝宝石】",
                "target_loc": "InsideJabuJabuBelly",
                "target_zh": "卓拉之泉 → 加卜加卜大人腹中",
                "how_to": "用空瓶捉一条鱼放在加卜加卜大人嘴前进入迷宫。里面拿到【回旋镖】后先护送露托公主踩开关，击败中首领大章鱼与首领【电击旋回虫 啪哩内德】即可集齐三颗精灵石！（别忘了顺手拿卓拉之泉右下角大妖精【法露尔之风】）",
            }
    elif not has_master_sword:
        cur = {
            "stage": "主线转折 · 打开时之门",
            "title": "集齐3颗精灵石！回【海拉鲁城堡前】捡【时之笛】并去【时之神殿】拔【大师之剑】",
            "target_loc": "TimeTemple",
            "target_zh": "海拉鲁城邑门前 → 时之神殿",
            "how_to": "靠近海拉鲁城邑门口触发剧情并潜入护城河拾取【时之笛】学会【时之歌】；进入城邑东侧【时之神殿】，站在台座前吹奏【时之歌】开门，上前拔出【大师之剑】进入7年后的成年篇章！",
        }
    elif not caps["hookshot"]:
        cur = {
            "stage": "成年主线 · 取得核心道具【钩索】",
            "title": "前往【卡卡利科村墓地】拉开丹培墓碑赛跑获【钩索】",
            "target_loc": "Graveyard",
            "target_zh": "卡卡利科村 → 墓地",
            "how_to": "去卡卡利科村墓地左侧找到唯一前面有花/独立可推的丹培墓碑，拉开跳下与丹培幽灵赛跑并紧跟终点，打开大宝箱获得【钩索】（没有钩索无法进森之神殿！顺路去风车小屋对大叔拿笛子学【岚之歌】）。",
        }
    elif not has_forest_m:
        cur = {
            "stage": "成年贤者 1/5 · 森之奖章",
            "title": "用【钩索】进入【森之神殿】并击败【来自异次元的恶灵 幻影加侬】",
            "target_loc": "ForestTemple",
            "target_zh": "迷途森林 → 森之圣域 → 森之神殿",
            "how_to": "穿过迷途森林到森之圣域（入口希克教【森之小步舞曲】），用【钩索】钩住门上方树枝进入森之神殿。先拿【妖精之弓】、击败幽灵四姐妹后打败首领【来自异次元的恶灵 幻影加侬】获得【森之奖章】。",
        }
    elif not has_fire_m:
        if not caps.get("goron_tunic", False):
            cur = {
                "stage": "成年贤者 2/5 · 火之奖章",
                "title": "去【鼓隆城】领【鼓隆服】，从密道进入【火之神殿】",
                "target_loc": "GoronCity" if curr_loc not in ("DeathMountainCrater", "FireTemple") else "FireTemple",
                "target_zh": "鼓隆城 → 死亡之山火山口 → 火之神殿",
                "how_to": "先用炸弹炸停鼓隆城滚动的小鼓隆获赠【鼓隆服】（或商店购买）并穿上，推开达鲁尼亚房间雕像走密道进死亡之山火山口（希克教【火之波丽露舞曲】），用【钩索】过断桥进入火之神殿解救鼓隆族、拿【百万吨锤】并击败首领【灼热穴居龙 瓦尔基亚】。",
            }
        else:
            cur = {
                "stage": "成年贤者 2/5 · 火之奖章",
                "title": "穿【鼓隆服】进【死亡之山火山口】攻略【火之神殿】",
                "target_loc": "FireTemple",
                "target_zh": "死亡之山火山口 → 火之神殿",
                "how_to": "你已拥有【鼓隆服】！穿上鼓隆服后从鼓隆城达鲁尼亚房间密道（或吹【火之波丽露舞曲】）进入死亡之山火山口，用【钩索】过断桥进入【火之神殿】，解救鼓隆族、取得【百万吨锤】并击败首领【灼热穴居龙 瓦尔基亚】获得【火之奖章】。",
            }
    elif not caps["iron_boots"]:
        cur = {
            "stage": "成年贤者 3/5 前置 · 冰之洞窟",
            "title": "前往【卓拉之泉 → 冰之洞窟】取得【铁靴】",
            "target_loc": "IceCavern",
            "target_zh": "卓拉领地 → 卓拉之泉 → 冰之洞窟",
            "how_to": "穿过冰冻的卓拉领地进入卓拉之泉，在浮冰间跳跃到达北侧洞口进入【冰之洞窟】；装蓝色火焰融化红冰拿【铁靴】并学【水之小夜曲】（顺便用一瓶蓝火回卓拉领地解冻卓拉王获赠【卓拉服】！）。",
        }
    elif not has_water_m:
        cur = {
            "stage": "成年贤者 3/5 · 水之奖章",
            "title": "穿【卓拉服】+【铁靴】潜入【水之神殿】拿【长钩索】并击败【水栖核细胞 摩法】",
            "target_loc": "WaterTemple",
            "target_zh": "海利亚湖畔 → 水之神殿",
            "how_to": "从海利亚湖畔潜入湖底大门进入水之神殿（穿【卓拉服】+【铁靴】、用【钩索】拉靶）。留意中央塔底升水位后的隐藏暗洞小钥匙，击败黑暗林克拿【长钩索】并打败首领【水栖核细胞 摩法】获得【水之奖章】。",
        }
    elif not _hb("IsGet.Armor_GlassTruth"):
        cur = {
            "stage": "成年贤者 4/5 前置 · 真实眼镜",
            "title": "学会【岚之歌】后回幼年下【井底】取得【真实眼镜】",
            "target_loc": "BottomOfTheWell",
            "target_zh": "卡卡利科村风车小屋 → 时之神殿插剑变幼年 → 井底",
            "how_to": "成年在风车小屋对大叔拿笛子学【岚之歌】；回时之神殿插剑变幼年，进风车小屋吹【岚之歌】抽干井水，跳入水井中央吹【塞尔达摇篮曲】放水，击败中首领死手拿【真实眼镜】。",
        }
    elif not has_shadow_m:
        cur = {
            "stage": "成年贤者 4/5 · 暗之奖章",
            "title": "学【暗之梦幻曲】进墓地深处攻略【暗之神殿】",
            "target_loc": "ShadowTemple",
            "target_zh": "卡卡利科村墓地高台 → 暗之神殿",
            "how_to": "先回卡卡利科村触发剧情（希克教【暗之梦幻曲】），吹曲传送到墓地高台用【迪荧之火】同时点燃大厅所有火把开门；全程配合【真实眼镜】与【浮空靴】击败首领【暗影魔幻兽 邦戈邦戈】获得【暗之奖章】。",
        }
    elif not has_spirit_m:
        cur = {
            "stage": "成年贤者 5/5 · 魂之奖章",
            "title": "救格鲁德木匠拿【格鲁德会员证】，穿越沙漠攻略【魂之神殿】（幼年→成年）",
            "target_loc": "SpiritTemple",
            "target_zh": "格鲁德要塞 → 幻影沙漠 → 魂之神殿",
            "how_to": "骑伊波娜（或用长钩索）过格鲁德之谷断桥进入格鲁德要塞，用【钩索】+【妖精之弓】救出4名木匠获【格鲁德会员证】；穿越幻影沙漠达巨大邪神像进出学【魂之慰灵曲】，先切幼年拿【银护手】，再切成年拿【镜盾】击败首领【双生魔导师 双子妖婆】获得【魂之奖章】。",
        }
    elif not has_light_arrow:
        cur = {
            "stage": "最终章前置 · 光箭",
            "title": "回【时之神殿】触发剧情领取【光箭】",
            "target_loc": "TimeTemple",
            "target_zh": "海拉鲁城邑 → 时之神殿",
            "how_to": "集齐五大神殿奖章后回到【时之神殿】内部触发最终剧情，从塞尔达手中接过【光箭】并开启通往加侬多夫城堡的彩虹桥。",
        }
    else:
        cur = {
            "stage": "最终决战 · 拯救塞尔达",
            "title": "攻入【加侬多夫城堡内部】破除六结界，决战【大魔王 加侬多夫】与【加侬】",
            "target_loc": "InsideGanonCastle",
            "target_zh": "加侬多夫城堡 → 加侬多夫城堡内部",
            "how_to": "过彩虹桥进入加侬多夫城堡内部，破解周围6大属性结界房间后登上中心高塔；用【光箭】+【大师之剑】击败【大魔王 加侬多夫】及最终魔王【加侬】（别忘了城堡外废墟巨石后的防御力加倍大妖精）。",
        }

    milestones = [
        ("科克里翡翠（德库树长老体内）", has_deku_stone),
        ("拜访塞尔达 & 塞尔达摇篮曲", has_letter),
        ("鼓隆红宝石（多东哥洞窟）", has_fire_stone),
        ("卓拉蓝宝石（加卜加卜大人腹中）", has_water_stone),
        ("拔出大师之剑（成年）", has_master_sword),
        ("取得钩索（墓地赛跑）", caps["hookshot"]),
        ("森之奖章（森之神殿）", has_forest_m),
        ("火之奖章（火之神殿）", has_fire_m),
        ("水之奖章（水之神殿）", has_water_m),
        ("暗之奖章（暗之神殿）", has_shadow_m),
        ("魂之奖章（魂之神殿）", has_spirit_m),
        ("神圣光箭（时之神殿）", has_light_arrow),
    ]
    cur["milestones"] = milestones
    cur["in_target_region"] = (curr_loc == cur["target_loc"])
    return cur


# Exact Boss & Mini-Boss Battle Definitions (adapted to Switch 2 OoT Remake Enemy.msbt & EnemyInfo_00)
BOSS_BATTLES: list[dict[str, Any]] = [
    {
        "id": "boss_gohma",
        "location": "InsideTheDekuTree",
        "name_zh": "寄生装甲蛛甲兽 哥玛",
        "is_miniboss": False,
        "valid_items": "妖精弹弓 · 德库坚果 · 德库木棒",
        "navi_hint": "它的甲壳很坚硬，等眼睛变红时用妖精弹弓或德库坚果击晕！",
        "tactics": [
            "1. 等哥玛眼睛变红（地面或天花板）时，用【妖精弹弓】或【德库坚果】射眼击晕。",
            "2. 击晕倒地后立刻上前用【跳劈】或【德库木棒】猛砍眼睛。",
            "3. 它爬上天花板产卵时快速射落，或优先清掉孵化出的幼体。",
        ],
        "arena_pos": (18.5, 60.0, 67.8),
        "arena_r": 26.0,
        "arena_dy": 16.0,
        "boss_rooms": [10],
        "appear_flags": ["InsideTheDekuTree_BossArea_ShutIn", "Gohma_IsLightingForBattle"],
        "defeat_flags": ["Gohma_DefeatBoss", "HaveDefeatedEnemy_Enemy_DungeonBoss_Gohma"],
        "journal_clear_flags": ["IsGet.Item_Stone_Forest"],
    },
    {
        "id": "miniboss_lizalfos",
        "location": "DodongoCavern",
        "name_zh": "蜥蜴战士（中首领）",
        "is_miniboss": True,
        "valid_items": "德库盾 / 海利亚盾 · 妖精弹弓 · 科克里之剑",
        "navi_hint": "一边举盾防御它们的挥砍，一边等待破绽反击！",
        "tactics": [
            "1. 用 Z 锁定单挑（同一时间只会有一只主动上来，另一只在旁观望）。",
            "2. 举盾防住连续挥剑后立刻跳劈，或用【德库坚果】定身连击。",
            "3. 二楼战斗时留意平台边缘，掉进熔岩会扣血。",
        ],
        "arena_pos": (96.0, 108.0, -45.0),
        "arena_r": 28.0,
        "arena_dy": 14.0,
        "appear_flags": ["DodongoCavern_AppearLizalfos_1F", "DodongoCavern_AppearLizalfos_2F"],
        "defeat_flags": ["DodongoCavern_Lizalfos_C_Dead", "DodongoCavern_Lizalfos_D_Dead"],
        "journal_clear_flags": ["IsGet.Item_Stone_Fire"],
        "require_pos_if_appear": True,
    },
    {
        "id": "boss_dodongo",
        "location": "DodongoCavern",
        "name_zh": "猛炎古代龙 多东哥王",
        "is_miniboss": False,
        "valid_items": "炸弹 / 炸弹花 · 海利亚盾",
        "navi_hint": "食欲特别旺盛、鳞片像岩石一样坚硬……让它吞下爆炸物！",
        "tactics": [
            "1. 等多东哥王张大嘴深吸气准备喷火时，把【炸弹】或【炸弹花】扔进嘴里！",
            "2. 肚子里炸响晕倒后立刻冲上去连续斩击（跳劈伤害最高）。",
            "3. 它卷成巨球冲撞时，靠在熔岩边角举【海利亚盾】蹲防即可完全弹开。",
        ],
        "arena_pos": (33.2, 73.5, -77.6),
        "arena_r": 26.0,
        "arena_dy": 12.0,
        "boss_rooms": [22],
        "appear_flags": ["Enemy_DungeonBoss_Dodongo_BossAppear"],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_Dodongo"],
        "journal_clear_flags": ["IsGet.Item_Stone_Fire"],
    },
    {
        "id": "miniboss_bigocto",
        "location": "InsideJabuJabuBelly",
        "name_zh": "大章鱼（中首领）",
        "is_miniboss": True,
        "valid_items": "回旋镖 · 德库坚果",
        "navi_hint": "从背后看它的弱点一清二楚，先用回旋镖定住它！",
        "tactics": [
            "1. 跑动躲开突刺，Z 锁定后趁它露出背后绿色弱点用【回旋镖】击中定身。",
            "2. 定身后立即追着背部的绿色弱点砍击（不要硬拼正面）。",
            "3. 如它快速旋转改变方向，向侧后翻滚拉开再找角度。",
        ],
        "arena_pos": (-38.5, 84.9, -90.4),
        "arena_r": 20.0,
        "arena_dy": 10.0,
        "appear_flags": ["Get_StoneOfWater_BigOctoAppear"],
        "defeat_flags": ["Get_StoneOfWater_BigOctoDefeat", "HaveDefeatedEnemy_Enemy_MiddleBoss_BigOcto"],
        "journal_clear_flags": ["IsGet.Item_Stone_Water"],
    },
    {
        "id": "boss_barinade",
        "location": "InsideJabuJabuBelly",
        "name_zh": "电击旋回虫 啪哩内德",
        "is_miniboss": False,
        "valid_items": "回旋镖 · 科克里之剑",
        "navi_hint": "多种怪物的集合体！先用回旋镖切断触手，再清带电水母！",
        "tactics": [
            "1. 第一阶段：边绕圈躲激光边用【回旋镖】切断连在天花板上的 3 根粗触手。",
            "2. 第二阶段：水母高速旋转时先避开；慢下来后用回旋镖击晕水母保护层。",
            "3. 第三阶段：击落全部外围水母后，用回旋镖定住本体电球并上前连斩。",
        ],
        "arena_pos": (42.3, 100.7, -112.1),
        "arena_r": 26.0,
        "arena_dy": 12.0,
        "boss_rooms": [15],
        "appear_flags": [],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_Barinade"],
        "journal_clear_flags": ["IsGet.Item_Stone_Water"],
    },
    {
        "id": "miniboss_meg",
        "location": "ForestTemple",
        "name_zh": "幽灵四姐妹·梅格（中首领）",
        "is_miniboss": True,
        "valid_items": "妖精之弓 · 钩索",
        "navi_hint": "分身和真身有一点差异，仔细观察旋转时与众不同的那一只！",
        "tactics": [
            "1. 四只梅格绕着你旋转时，只有【原地转了一圈】的那一只才是真身！",
            "2. 用【妖精之弓】或【钩索】快速锁定真身射击即可扣血（打假身会反击）。",
            "3. 击败她就能激活中央电梯前往森之神殿底层首领门。",
        ],
        "arena_pos": (0.0, 100.1, -3.5),
        "arena_r": 20.0,
        "arena_dy": 10.0,
        "appear_flags": ["ForestTemple_MegBattleStart"],
        "defeat_flags": ["ForestTemple_DefeatMeg", "HaveDefeatedEnemy_Enemy_MiddleBoss_Poe_Meg"],
        "journal_clear_flags": ["IsGet.Item_Medal_Forest"],
    },
    {
        "id": "boss_phantom_ganon",
        "location": "ForestTemple",
        "name_zh": "来自异次元的恶灵 幻影加侬",
        "is_miniboss": False,
        "valid_items": "妖精之弓 · 大师之剑",
        "navi_hint": "它身缠气场时攻击无效，先把画里的真身射下来，再用大师之剑弹回光球！",
        "tactics": [
            "1. 第一阶段：观察四周 6 幅壁画，亮紫黑光且【冲出画面不折返】的是真马，用【妖精之弓】射它！",
            "2. 第二阶段：幻影加侬悬浮投掷光球时，用【大师之剑】挥砍把光球打回去对弹。",
            "3. 被弹中击晕坠地后立刻冲上前连砍，重复 2~3 轮即可击败。",
        ],
        "arena_pos": (-0.1, 80.9, -62.6),
        "arena_r": 25.0,
        "arena_dy": 12.0,
        "boss_rooms": [29],
        "appear_flags": ["ForestTemple_SageOfForest_BossAppearance"],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_PhantomGanon"],
        "journal_clear_flags": ["IsGet.Item_Medal_Forest"],
    },
    {
        "id": "miniboss_flare_dancer",
        "location": "FireTemple",
        "name_zh": "火舞者（中首领）",
        "is_miniboss": True,
        "valid_items": "钩索 · 炸弹 · 大师之剑",
        "navi_hint": "身缠火焰时剑弓无效！先用钩索把中心黑色主体拽出来！",
        "tactics": [
            "1. 绕圈躲开地面火柱，用【钩索】瞄准火衣胸口的黑色核心直接拉出本体。",
            "2. 若手头有【炸弹】，在它冲过路径提前放炸弹也能炸脱火衣。",
            "3. 本体惊慌绕场地乱跑时立刻追上去狂砍（注意别撞到火焰圈）。",
        ],
        "arena_pos": (-7.0, 102.0, -33.3),
        "arena_pos_alt": (-71.9, 150.0, 2.4),
        "arena_r": 18.0,
        "arena_dy": 10.0,
        "boss_rooms": [3, 24],
        "appear_flags": [],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_MiddleBoss_FlareDancer"],
        "journal_clear_flags": ["IsGet.Item_Medal_Fire"],
    },
    {
        "id": "boss_volvagia",
        "location": "FireTemple",
        "name_zh": "灼热穴居龙 瓦尔基亚",
        "is_miniboss": False,
        "valid_items": "百万吨锤 · 鼓隆服 · 大师之剑",
        "navi_hint": "鳞片极硬，趁它从熔岩洞冒头时用百万吨锤狠狠敲击头部！",
        "tactics": [
            "1. 务必穿着【鼓隆服】防高温！观察哪一个熔岩洞冒出黑烟火焰。",
            "2. 龙头一探出洞口立刻用【百万吨锤】敲晕，接着换大师之剑疯狂输出或再锤。",
            "3. 它飞到空中喷火或落石时，绕平台边缘跑动或挂在平台最外沿可无伤躲避。",
        ],
        "arena_pos": (-80.6, 93.3, 16.3),
        "arena_r": 26.0,
        "arena_dy": 14.0,
        "boss_rooms": [33],
        "appear_flags": ["Enemy_DungeonBoss_Volvagia_BossAppear", "FireTemple_BossGroundChange"],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_Volvagia"],
        "journal_clear_flags": ["IsGet.Item_Medal_Fire"],
    },
    {
        "id": "miniboss_dark_link",
        "location": "WaterTemple",
        "name_zh": "黑暗林克（中首领）",
        "is_miniboss": True,
        "valid_items": "大鼓隆之剑 · 迪荧之火 · 百万吨锤（禁用Z锁定！）",
        "navi_hint": "不要用 Z 锁定正面拼剑！无锁定强攻或用迪荧之火/百万吨锤克制！",
        "tactics": [
            "1. 千万【不要按 Z 锁定】——你一锁定他就会完美格挡并踩你的剑！",
            "2. 推荐无锁定用【迪荧之火】直接烧，或用【百万吨锤】/【大鼓隆之剑】无锁定横劈。",
            "3. 击败他后房间解除封锁，前方宝箱就是【长钩索】！",
        ],
        "arena_pos": (-78.5, 126.3, -63.5),
        "arena_r": 26.0,
        "arena_dy": 10.0,
        "appear_flags": ["WaterTemple_DarkLink_InBattle", "WaterTemple_DarkLinkRoom_Locked"],
        "defeat_flags": ["WaterTemple_DarkLink_Death", "HaveDefeatedEnemy_Enemy_MiddleBoss_DarkLink"],
        "journal_clear_flags": ["IsGet.Item_Longshot", "IsGet.Item_Medal_Water"],
    },
    {
        "id": "boss_morpha",
        "location": "WaterTemple",
        "name_zh": "水栖核细胞 摩法",
        "is_miniboss": False,
        "valid_items": "长钩索 · 大师之剑 / 大鼓隆之剑",
        "navi_hint": "在水里毫无胜算，站在角落平台上用长钩索把水柱里的红核拉出来！",
        "tactics": [
            "1. 站在大厅四周的墙角石头平台上（避开水池中央，防止被触手甩进水里）。",
            "2. 用【长钩索】对准水柱里游动的红色细胞核直接拉扯到岸上！",
            "3. 红核落地后迅速上前连续斩击；两根触手阶段留意背后防抓即可。",
        ],
        "arena_pos": (-4.5, 129.3, -91.8),
        "arena_r": 26.0,
        "arena_dy": 14.0,
        "boss_rooms": [23],
        "appear_flags": [],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_Morpha"],
        "journal_clear_flags": ["IsGet.Item_Medal_Water"],
    },
    {
        "id": "miniboss_dead_hand_well",
        "location": "BottomOfTheWell",
        "name_zh": "死手（井底·中首领）",
        "is_miniboss": True,
        "valid_items": "科克里之剑 · 炸弹",
        "navi_hint": "故意被长手抓住引出主体，挣脱后集中攻击露出来的脸部！",
        "tactics": [
            "1. 故意靠近房间里任意一只白色长手，被它抓住后主体才会从地下钻出！",
            "2. 狂按方向键/攻击键挣脱（或等主体走近低头准备咬你时挣脱）。",
            "3. 趁它低头露出脸部的瞬间用剑连砍头部（周围的手不必管），击败拿【真实眼镜】！",
        ],
        "arena_pos": (-0.2, 92.3, -105.1),
        "arena_r": 16.0,
        "arena_dy": 8.0,
        "boss_rooms": [8],
        "appear_flags": ["BottomOfTheWell_Level_Room_06_Boss_Appear"],
        "defeat_flags": ["BottomOfTheWell_Level_Room_06_Boss_Defeat"],
        "journal_clear_flags": ["IsGet.Armor_GlassTruth"],
    },
    {
        "id": "miniboss_dead_hand_shadow",
        "location": "ShadowTemple",
        "name_zh": "死手（暗之神殿·中首领）",
        "is_miniboss": True,
        "valid_items": "真实眼镜 · 大师之剑 · 炸弹",
        "navi_hint": "开真实眼镜看破地面隐形位置，被白手抓住引出主体并猛攻头部！",
        "tactics": [
            "1. 开启【真实眼镜】可看清地下潜行的本体与隐形白手位置。",
            "2. 主动被白手抓住触发本体现身，挣脱后趁其低头咬人时用【大师之剑】跳劈头部。",
            "3. 击败后出现宝箱获得【浮空靴】！",
        ],
        "arena_pos": (-75.0, 90.4, -10.2),
        "arena_r": 16.0,
        "arena_dy": 8.0,
        "boss_rooms": [4],
        "appear_flags": [],
        "defeat_flags": ["ShadowTemple_Level_Room_B1F_D_Defeat_DeadHand"],
        "journal_clear_flags": ["IsGet.Armor_Adult_HoverBoot", "IsGet.Item_Medal_Shadow"],
    },
    {
        "id": "boss_bongo",
        "location": "ShadowTemple",
        "name_zh": "暗影魔幻兽 邦戈邦戈",
        "is_miniboss": False,
        "valid_items": "真实眼镜 · 妖精之弓 · 浮空靴 · 大师之剑",
        "navi_hint": "穿浮空靴稳住脚步，先射晕两只巨手，再开真实眼镜射中隐形本体的红眼！",
        "tactics": [
            "1. 建议穿【浮空靴】减少鼓面震动弹跳；先用【妖精之弓】依次射晕左右两只巨手。",
            "2. 两只手全击晕后立刻开启【真实眼镜】，看清隐形本体正面的大红眼！",
            "3. 等本体冲刺过来时一箭射眼击晕，冲上去用大师之剑/大鼓隆之剑疯狂输出。",
        ],
        "arena_pos": (-138.3, -11.5, 48.1),
        "arena_r": 26.0,
        "arena_dy": 14.0,
        "boss_rooms": [24],
        "appear_flags": ["ShadowTemple_Level_StartBossBattle"],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_BongoBongo"],
        "journal_clear_flags": ["IsGet.Item_Medal_Shadow"],
    },
    {
        "id": "miniboss_nabooru",
        "location": "SpiritTemple",
        "name_zh": "铁甲武士·娜波露（中首领）",
        "is_miniboss": True,
        "valid_items": "跳劈反击 · 炸弹",
        "navi_hint": "巨斧一击连盾都挡不住，诱使她挥斧砸空后趁硬直跳劈破甲！",
        "tactics": [
            "1. 靠近引诱她挥动巨斧横扫/重砸，立刻后跳躲开（盾牌挡不住巨斧重击）。",
            "2. 趁她收斧硬直时上前跳劈一次，再立刻后跳拉开，切勿贪刀。",
            "3. 打掉铠甲后她移动速度暴增，保持距离继续诱招反击即可（也可以扔炸弹炸甲）。",
        ],
        "arena_pos": (0.0, 135.0, -95.5),
        "arena_r": 18.0,
        "arena_dy": 10.0,
        "boss_rooms": [32],
        "appear_flags": ["Enemy_MiddleBoss_IronKnuckle_Nabooru_BossAppear", "SageOfSpirit_Nabooru_On"],
        "defeat_flags": ["Enemy_MiddleBoss_IronKnuckle_Nabooru_BossDefeat", "HaveDefeatedEnemy_Enemy_MiddleBoss_IronKnuckle_Nabooru"],
        "journal_clear_flags": ["IsGet.Item_Medal_Spirit"],
    },
    {
        "id": "boss_twinrova",
        "location": "SpiritTemple",
        "name_zh": "双生魔导师 双子妖婆（小竹＆小梅）",
        "is_miniboss": False,
        "valid_items": "镜盾 · 大师之剑 / 大鼓隆之剑",
        "navi_hint": "用镜盾把冰魔法反射给火魔女、火魔法反射给冰魔女；合体后连续吸收同属性3次反击！",
        "tactics": [
            "1. 第一阶段：站在高台柱子上举起【镜盾】，把小梅(火)的光束反射打向小竹(冰)，反之亦然！",
            "2. 第二阶段（合体）：举【镜盾】连续吸收【同一种属性魔法 3 次】（例如连续吸 3 发冰或 3 发火）！",
            "3. 吸满 3 次镜盾会自动射出反击激光击晕双子妖婆，跳上中央平台猛砍！",
        ],
        "arena_pos": (12.7, 144.7, -145.3),
        "arena_r": 25.0,
        "arena_dy": 16.0,
        "boss_rooms": [33],
        "appear_flags": ["SageOfSpirit_BossIn", "Enemy_DungeonBoss_TwinrovaChange", "SpiritTemple_Boss_IsSplit", "SpiritTemple_Boss_IsCombine"],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_Twinrova"],
        "journal_clear_flags": ["IsGet.Item_Medal_Spirit"],
    },
    {
        "id": "boss_ganondorf",
        "location": "InsideGanonCastle",
        "name_zh": "大魔王 加侬多夫",
        "is_miniboss": False,
        "valid_items": "光箭 · 大师之剑 · 空瓶（可反弹光球）",
        "navi_hint": "用剑把光球打回去对弹，命中后再用光箭射晕并跳到中央平台砍击！",
        "tactics": [
            "1. 站在周围四根高台上，用【大师之剑】或【空瓶】把加侬多夫发射的黄色光球打回去对弹。",
            "2. 蓄力五连紫弹时用回旋斩一次性全弹回！",
            "3. 把他打晕在空中后立刻切换【光箭】射中他，再跳向中央高台狂砍！",
        ],
        "arena_pos": (0.1, 174.1, -24.6),
        "arena_r": 26.0,
        "arena_dy": 16.0,
        "boss_rooms": [26, 63],
        "appear_flags": ["InsideGanonCastle_IsBossAppearDemo", "InsideGanonCastle_IsEnterBossRoom"],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_Ganondorf"],
        "journal_clear_flags": ["FinalBattleField_ChangeENVForBoss", "HaveDefeatedEnemy_Enemy_DungeonBoss_Ganon"],
    },
    {
        "id": "boss_ganon",
        "location": "GanonCastle",
        "name_zh": "最终魔王 加侬",
        "is_miniboss": False,
        "valid_items": "光箭 · 百万吨锤 / 大鼓隆之剑 · 德库坚果 · 大师之剑",
        "navi_hint": "前期没有大师之剑时可用百万吨锤/大鼓隆之剑穿裆打尾巴！取回大师之剑后用光箭射晕斩杀！",
        "tactics": [
            "1. 开局大师之剑被拍飞：用【光箭】射脸或【德库坚果】定身，贴近穿裆绕背用【百万吨锤】或【大鼓隆之剑】砸尾巴！",
            "2. 火焰壁消失后冲向火焰边取回【大师之剑】，从此装备大师之剑输出尾巴。",
            "3. 塞尔达魔法束缚住加侬时，冲上去给头部致命一击终结游戏！",
        ],
        "arena_pos": (-1.4, 100.0, -1.0),
        "arena_r": 32.0,
        "arena_dy": 16.0,
        "appear_flags": ["FinalBattleField_ChangeENVForBoss", "FinalBattleField_DefeatGanonStart", "FinalBattleField_Create_Ganon_SecondHalfBattle"],
        "defeat_flags": ["HaveDefeatedEnemy_Enemy_DungeonBoss_Ganon"],
        "journal_clear_flags": [],
    },
]


def detect_active_boss(
    curr_loc: str,
    kv: dict[int, int],
    cap_hashes: dict[str, int],
    player_pos: tuple[float, float, float] | None,
    dungeon_room: int | None = None,
) -> dict[str, Any] | None:
    """Detect whether the player is currently engaged in a Boss or Mini-Boss battle.
    Uses triple-redundant signals (Boss Bool flags + real-time DungeonRoom + IsBossBattle),
    because Player_Pos_For_Map freezes outside Boss Doors when the Minimap hides."""
    from save_reader import BOSS_DEFEAT_INT_HASHES

    def _hb(k: str) -> bool:
        h = cap_hashes.get(k)
        if not h:
            return False
        if kv.get(h, 0):
            return True
        sub_h = BOSS_DEFEAT_INT_HASHES.get(h)
        return bool(kv.get(sub_h, 0)) if sub_h else False

    def _in_arena(b: dict[str, Any]) -> bool:
        if not player_pos:
            return False
        px, py, pz = player_pos
        r = b["arena_r"]
        dy_max = b["arena_dy"]
        for key in ("arena_pos", "arena_pos_alt"):
            pos = b.get(key)
            if pos:
                ax, ay, az = pos
                if ((px - ax) ** 2 + (pz - az) ** 2) <= (r * r) and abs(py - ay) <= dy_max:
                    return True
        return False

    is_boss_battle_global = _hb("IsBossBattle")

    for b in BOSS_BATTLES:
        # Match scene (Ganon final stage can report DreamWorld or GanonCastle)
        if b["location"] != curr_loc and not (b["id"] == "boss_ganon" and curr_loc in ("GanonCastle", "DreamWorld", "InsideGanonCastle")):
            continue

        if b["id"] == "miniboss_flare_dancer":
            r03_dead = _hb("FireTemple_Room03_FlareDancerisDead")
            r24_dead = _hb("FireTemple_Room24_FlareDancerisDead")
            if r03_dead and r24_dead:
                continue
            if (dungeon_room == 3 and not r03_dead) or (dungeon_room == 24 and not r24_dead):
                return b
            if player_pos:
                px, py, pz = player_pos
                in_03 = ((px + 7.0) ** 2 + (pz + 33.3) ** 2) <= 324.0 and abs(py - 102.0) <= 10.0
                in_24 = ((px + 71.9) ** 2 + (pz - 2.4) ** 2) <= 324.0 and abs(py - 150.0) <= 10.0
                if (in_03 and not r03_dead) or (in_24 and not r24_dead):
                    return b
            continue

        if b["id"] == "miniboss_lizalfos":
            c_dead = _hb("DodongoCavern_Lizalfos_C_Dead")
            d_dead = _hb("DodongoCavern_Lizalfos_D_Dead")
            if c_dead and d_dead:
                continue
            if (dungeon_room == 5 and not c_dead) or (dungeon_room == 16 and not d_dead):
                return b
            in_arena = _in_arena(b)
            if in_arena and ((_hb("DodongoCavern_AppearLizalfos_1F") and not c_dead) or (_hb("DodongoCavern_AppearLizalfos_2F") and not d_dead)):
                return b
            continue

        def_flags = b.get("defeat_flags", [])
        if any(_hb(f) for f in def_flags):
            continue

        boss_rooms = b.get("boss_rooms") or []
        in_boss_room = dungeon_room is not None and dungeon_room in boss_rooms
        app_flags = b.get("appear_flags", [])
        appear_on = any(_hb(f) for f in app_flags)
        in_arena = _in_arena(b)

        # 1. Exact DungeonRoom match for dedicated Boss/Mini-Boss rooms (unaffected by hidden Minimap!)
        if in_boss_room:
            return b

        # 2. Global IsBossBattle flag for main Dungeon Bosses in their matching scene
        if not b["is_miniboss"] and is_boss_battle_global:
            if b["id"] == "boss_ganon" and curr_loc == "InsideGanonCastle":
                pass  # InsideGanonCastle belongs to Ganondorf; Ganon is outside on GanonCastle / FinalBattleField
            else:
                return b

        # 3. Dedicated Boss/Mini-Boss appear Bool flags
        if appear_on:
            if b.get("require_pos_if_appear") and not in_arena:
                continue
            return b

        # 4. Fallback arena coordinate check when no appear_flags exist
        if not app_flags and in_arena:
            return b
    return None


def evaluate_boss_journal(
    curr_loc: str,
    story: dict[str, Any],
    active_boss: dict[str, Any] | None,
    kv: dict[int, int],
    cap_hashes: dict[str, int],
    unlocked_boss_ids: set[str],
    unlocked_tip_locs: set[str],
) -> dict[str, Any]:
    """Compute progressive anti-spoiler Boss & Mechanic journal:
    - Unlock a Boss/Mini-Boss ONLY when Main Story reaches its dungeon, the player enters/approaches its dungeon/arena, or it is defeated.
    - Partition into unlocked_undefeated (expanded at top) and defeated (collapsed in green at bottom)."""
    from save_reader import BOSS_DEFEAT_INT_HASHES

    def _hb(k: str) -> bool:
        h = cap_hashes.get(k)
        if not h:
            return False
        if kv.get(h, 0):
            return True
        sub_h = BOSS_DEFEAT_INT_HASHES.get(h)
        return bool(kv.get(sub_h, 0)) if sub_h else False

    story_target = story.get("target_loc", "")
    story_stage = story.get("stage", "")
    # If story is at GoronCity for Goron Tunic right before Fire Temple, FireTemple is also the active story dungeon
    story_dungeons = {story_target}
    if "火之奖章" in story_stage:
        story_dungeons.add("FireTemple")

    unlocked_undefeated: list[dict[str, Any]] = []
    defeated: list[dict[str, Any]] = []
    locked_count = 0

    for b in BOSS_BATTLES:
        bid = b["id"]
        bloc = b["location"]
        if bid == "miniboss_flare_dancer":
            is_def = (
                (_hb("FireTemple_Room03_FlareDancerisDead") and _hb("FireTemple_Room24_FlareDancerisDead"))
                or _hb("HaveDefeatedEnemy_Enemy_MiddleBoss_FlareDancer")
                or any(_hb(f) for f in b.get("journal_clear_flags", []))
            )
        elif bid == "miniboss_lizalfos":
            is_def = (
                (_hb("DodongoCavern_Lizalfos_C_Dead") and _hb("DodongoCavern_Lizalfos_D_Dead"))
                or any(_hb(f) for f in b.get("journal_clear_flags", []))
            )
        else:
            is_def = any(_hb(f) for f in b.get("defeat_flags", [])) or any(_hb(f) for f in b.get("journal_clear_flags", []))

        appear_on = any(_hb(f) for f in b.get("appear_flags", []))
        is_active = bool(active_boss and active_boss["id"] == bid)
        in_scene = (curr_loc == bloc) or (bid == "boss_ganon" and curr_loc == "GanonCastle")
        in_story = (bloc in story_dungeons) or (bid == "boss_ganon" and story_target == "InsideGanonCastle" and _hb("HaveDefeatedEnemy_Enemy_DungeonBoss_Ganondorf"))

        if is_def or is_active or appear_on or in_scene or in_story or (bid in unlocked_boss_ids):
            unlocked_boss_ids.add(bid)
            unlocked_tip_locs.add(bloc)
            if is_def:
                defeated.append(b)
            else:
                unlocked_undefeated.append(b)
        else:
            locked_count += 1

    # Prioritize active boss / current scene / current story target in unlocked_undefeated
    unlocked_undefeated.sort(
        key=lambda b: (
            0 if (active_boss and active_boss["id"] == b["id"]) else (1 if b["location"] == curr_loc else (2 if b["location"] in story_dungeons else 3)),
            1 if b["is_miniboss"] else 0,
        )
    )

    # Also unlock non-boss mechanic tip locations when reached by story, visited, or cleared
    if curr_loc in BOSS_AND_MECHANIC_TIPS:
        unlocked_tip_locs.add(curr_loc)
    if story_target in BOSS_AND_MECHANIC_TIPS:
        unlocked_tip_locs.add(story_target)
    if _hb("IsGet.Item_Scale_Silver") or _hb("IsGet.Item_Stone_Water"):
        unlocked_tip_locs.add("ZoraDomain")
    if _hb("HavePlayedEvent.Dm_ZoraFountain_0000") or _hb("IsGet.Item_Stone_Water"):
        unlocked_tip_locs.add("ZoraFountain")
    if _hb("IsGet.Armor_Adult_HeavyBoot") or _hb("IsGet.Item_Medal_Water"):
        unlocked_tip_locs.add("IceCavern")

    active_tip_locs: dict[str, list[tuple[str, str]]] = {}
    cleared_tip_locs: dict[str, list[tuple[str, str]]] = {}
    locked_tip_locs_count = 0

    # Determine which unlocked tip locations are still active vs fully cleared
    undefeated_locs = {b["location"] for b in unlocked_undefeated}
    defeated_locs = {b["location"] for b in defeated}

    ordered_keys: list[str] = []
    for k in [curr_loc, story_target] + list(BOSS_AND_MECHANIC_TIPS.keys()):
        if k in BOSS_AND_MECHANIC_TIPS and k not in ordered_keys:
            ordered_keys.append(k)

    for loc in ordered_keys:
        if loc not in unlocked_tip_locs:
            locked_tip_locs_count += 1
            continue
        is_cleared_loc = (
            loc != curr_loc
            and loc not in story_dungeons
            and loc not in undefeated_locs
            and (
                loc in defeated_locs
                or (loc == "ZoraDomain" and _hb("IsGet.Item_Stone_Water"))
                or (loc == "ZoraFountain" and _hb("IsGet.Item_Stone_Water"))
                or (loc == "IceCavern" and _hb("IsGet.Item_Medal_Water"))
            )
        )
        if is_cleared_loc:
            cleared_tip_locs[loc] = BOSS_AND_MECHANIC_TIPS[loc]
        else:
            active_tip_locs[loc] = BOSS_AND_MECHANIC_TIPS[loc]

    return {
        "unlocked_undefeated": unlocked_undefeated,
        "defeated": defeated,
        "locked_count": locked_count,
        "active_tips": active_tip_locs,
        "cleared_tips": cleared_tip_locs,
        "locked_tip_locs_count": locked_tip_locs_count,
    }


# Cross-region border & route links: items right outside a region's fence/gate or reached via the current region
# Each entry: (target_item_id_or_loc_prefix, bridge_hint)
#   If target starts with "loc:", includes ALL currently reachable uncollected items in that adjacent region.
REGION_ADJACENT_LINKS: dict[str, list[tuple[str, str]]] = {
    "LonLonRanch": [
        ("gs_a6a4e87da18fa678", "牧场正南外墙外紧邻树丛（出大门绕到牧场南侧外墙用炸弹炸开地面石洞）"),
        ("gs_7d8ec14bdd1f6341", "牧场东南侧平原地面隐藏炸弹洞（靠近响音石会震动）"),
        ("hp_hf_fence", "牧场西侧往格鲁德/海利亚湖平原巨石旁隐蔽炸弹洞水底"),
    ],
    "KakarikoVillage": [
        ("loc:DeathMountainTrail", "从村北门守卫旁上去即达【死亡之山登山道】"),
        ("loc:Graveyard", "从村东侧出口过去即达【墓地】"),
        ("gs_1e38e8d23596eecf", "出村西门路口第 1 棵单树（翻滚撞树落下）"),
        ("hp_hf_scrub", "出村西门单树旁地面隐藏炸弹洞德库商人（10卢比）"),
    ],
    "DeathMountainTrail": [
        ("hp_kak_cow", "爬到山顶抓猫头鹰可飞降落到卡卡利科村南【英帕家牛棚笼内】拿心之碎片"),
        ("loc:GoronCity", "山腰进入即达【鼓隆城】"),
        ("loc:DeathMountainCrater", "山顶洞口爬入即达【死亡之山火山口】"),
    ],
    "GoronCity": [
        ("hp_dmt_cavern", "出鼓隆城往下走即到多东哥洞窟门前（幼年门前种魔法豆/成年飞叶上崖壁）"),
        ("loc:DeathMountainCrater", "推开底层雕像/成年达鲁尼亚房间通道直通【死亡之山火山口】"),
    ],
    "Graveyard": [
        ("hp_kak_windmill", "成年丹培赛跑终点出口可直通【卡卡利科村风车高台】心之碎片"),
    ],
    "KokiriForest": [
        ("loc:LostWood", "从森林北侧通道上去即达【迷途森林】"),
    ],
    "LostWood": [
        ("loc:SacredForestMeadow", "科奇里进按【右→左→右→左→直走→左→右】；鼓隆城捷径进按【左→左→直走→左→右】即达【森之圣域】"),
    ],
    "Market": [
        ("loc:HyruleCastle", "从城邑北侧上去即达【海拉鲁城堡】"),
        ("loc:TimeTemple", "城邑东侧进入即达【时之神殿】"),
    ],
    "HyruleField": [
        ("loc:LonLonRanch", "平原中央即【荣蓉牧场】（内外有黄金骷髅蜘蛛与牛棚心之碎片）"),
    ],
    "ZoraRiver": [
        ("loc:ZoraDomain", "沿河流上游瀑布吹塞尔达摇篮曲进入【卓拉领地】"),
    ],
    "ZoraDomain": [
        ("loc:ZoraFountain", "穿过王座后方通道（幼年需先给卓拉王瓶中信）进入【卓拉之泉】"),
        ("q_lh_ruto_letter", "水底捷径潜入直通【海利亚湖畔】北岸捡【瓶中信】"),
    ],
    "LakeHylia": [
        ("hp_hf_fence", "出湖畔北门向西北平原栅栏外巨石下炸弹洞水底"),
    ],
    "GerudoValley": [
        ("loc:GerudoFortress", "过断桥（骑伊波娜飞跃或用长钩索）即达【格鲁德要塞】"),
    ],
    "GerudoFortress": [
        ("loc:HountedWasteland", "救完4名木匠拿格鲁德会员证后打开北门进入【幻影沙漠】"),
    ],
    "HountedWasteland": [
        ("loc:DesertColossus", "穿越大沙漠（开真实眼镜跟幽灵引路者）即达【巨大邪神像】"),
    ],
}


def get_adjacent_reachable_items(
    loc: str,
    all_items: list["EvaluatedItem"],
) -> list[tuple[str, "EvaluatedItem"]]:
    """Return reachable uncollected items in adjacent/linked regions with bridge hints."""
    links = REGION_ADJACENT_LINKS.get(loc, [])
    if not links:
        return []
    by_id = {it.id: it for it in all_items}
    out: list[tuple[str, EvaluatedItem]] = []
    seen: set[str] = set()
    for target, hint in links:
        if target.startswith("loc:"):
            tloc = target[4:]
            for it in all_items:
                if it.location == tloc and not it.collected and it.reachable and it.id not in seen:
                    seen.add(it.id)
                    out.append((hint, it))
        else:
            it = by_id.get(target)
            if it and not it.collected and it.reachable and it.id not in seen:
                seen.add(it.id)
                out.append((hint, it))
    return out


MAGIC_BEAN_SOIL_SPECS: list[dict[str, Any]] = [
    {
        "loc": "KokiriForest",
        "name": "商店旁软土",
        "flags": ("Gimmick_MagicBeanSoil_KokiriForest",),
        "skull_id": "gs_858f5000ad57b2cc",
        "tier": "skip",
        "rewards": (),
        "pos": (8.2, 112.4, -23.3),
        "why": "成年飞叶仅用来拿高台卢比，无心之碎片或黄金蜘蛛",
    },
    {
        "loc": "LostWood",
        "name": "森之舞台草坪软土",
        "flags": ("Gimmick_MagicBeanSoil_LostWood01",),
        "skull_id": "gs_f6fa6ef0ca152948",
        "tier": "opt",
        "rewards": ("gs_3c2b585ac5c0443e",),
        "pos": (10.9, 99.5, -52.1),
        "why": "成年乘飞叶直达树干拿蜘蛛（不种也可等水之神殿拿长钩索来取）",
    },
    {
        "loc": "LostWood",
        "name": "科奇里入口左转木桥旁软土",
        "flags": ("Gimmick_MagicBeanSoil_LostWood02",),
        "skull_id": "gs_8186bcb07d6c2cf9",
        "tier": "skip",
        "rewards": (),
        "pos": (-33.2, 99.9, 31.4),
        "why": "成年飞叶仅用来拿高处卢比，无独占收集品",
    },
    {
        "loc": "Graveyard",
        "name": "墓地左侧软土",
        "flags": ("Gimmick_MagicBeanSoil_Graveyard",),
        "skull_id": "gs_e91f6be796358ffc",
        "tier": "must",
        "rewards": ("hp_gy_bean",),
        "pos": (-12.1, 103.1, -12.2),
        "why": "成年乘飞叶上东侧高台破木箱拿【1块心之碎片】",
    },
    {
        "loc": "DeathMountainTrail",
        "name": "多东哥洞窟入口前软土",
        "flags": ("Gimmick_MagicBeanSoil_DeathMountainTrail",),
        "skull_id": "gs_f1d32c06612da232",
        "tier": "must",
        "rewards": ("hp_dmt_cavern",),
        "pos": (-45.5, 108.9, -20.2),
        "why": "成年乘飞叶上洞窟口正上方崖壁拿【1块心之碎片】",
    },
    {
        "loc": "DeathMountainCrater",
        "name": "火山口传送点旁软土",
        "flags": ("Gimmick_MagicBeanSoil_DeathMountainCrater",),
        "skull_id": "gs_58c75badf059ca54",
        "tier": "must",
        "rewards": ("hp_dmc_volcano",),
        "pos": (3.8, 110.9, -0.8),
        "why": "成年乘飞叶上火山口中央高塔顶拿【1块心之碎片】",
    },
    {
        "loc": "ZoraRiver",
        "name": "入口魔法豆商人旁软土",
        "flags": ("Gimmick_MagicBeanSoil_ZoraRiver", "Gimmick_MagicBeanSoil_ZoraRiver02"),
        "skull_id": "gs_abad0e9f0d471156",
        "tier": "skip",
        "rewards": (),
        "pos": (-54.6, 100.3, -11.9),
        "why": "成年飞叶仅作过河捷径；河畔两块心片靠幼年抱鸡滑翔即可全拿",
    },
    {
        "loc": "LakeHylia",
        "name": "湖畔实验室旁软土",
        "flags": ("Gimmick_MagicBeanSoil_LakeHylia",),
        "skull_id": "gs_61576befd16c499a",
        "tier": "opt",
        "rewards": ("hp_lh_roof",),
        "pos": (-167.7, 137.6, 413.5),
        "why": "成年乘飞叶直上实验室屋顶拿【1块心之碎片】（不种需长钩索+稻草人，短钩索够不到）",
    },
    {
        "loc": "GerudoValley",
        "name": "桥下水边软土",
        "flags": ("Gimmick_MagicBeanSoil_GerudoValley",),
        "skull_id": "gs_738f5746cc517702",
        "tier": "skip",
        "rewards": (),
        "pos": (-11.0, 47.8, 2.4),
        "why": "成年飞叶仅拿谷底卢比；峡谷两块心片靠抱鸡滑翔或长钩索即可",
    },
    {
        "loc": "DesertColossus",
        "name": "魂之神殿入口右侧软土",
        "flags": ("Gimmick_MagicBeanSoil_DesertColossus",),
        "skull_id": "gs_341f2c03598c861",
        "tier": "must",
        "rewards": ("hp_dc_arch", "gs_d0f7e5ffa76ba288"),
        "pos": (-157.5, 95.4, 17.2),
        "why": "成年乘飞叶一次拿【石拱门心之碎片 + 东北石台夜间蜘蛛】",
    },
]


def compute_bean_soil_tips(
    loc: str,
    caps: dict[str, Any],
    kv: dict[int, int],
    cap_hashes: dict[str, int],
    collected_ids: set[str],
    player_pos: tuple[float, float, float] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sp in MAGIC_BEAN_SOIL_SPECS:
        if sp["loc"] != loc:
            continue
        planted = any(bool(kv.get(cap_hashes.get(fk, 0), 0)) for fk in sp["flags"] if fk in cap_hashes)
        rewards_done = bool(sp["rewards"]) and all(rid in collected_ids for rid in sp["rewards"])
        alt_ready = (
            (sp["loc"] == "LostWood" and sp["tier"] == "opt" and bool(caps.get("longshot")))
            or (sp["loc"] == "LakeHylia" and sp["tier"] == "opt" and bool(caps.get("scarecrow_longshot")))
        )
        if planted:
            tier_eff = "done"
            badge_txt = "✅ 此土坑已种魔法豆"
            need_plant = False
        elif rewards_done:
            tier_eff = "done"
            badge_txt = "✅ 不用再种魔法豆（成年奖励已全拿）"
            need_plant = False
        elif sp["tier"] == "must":
            tier_eff = "must"
            badge_txt = "🔴 必种魔法豆！"
            need_plant = True
        elif sp["tier"] == "opt":
            if alt_ready:
                tier_eff = "skip"
                badge_txt = "✅ 可不种（你已具备长钩索替代方案）"
                need_plant = False
            else:
                tier_eff = "opt"
                badge_txt = "🟡 推荐顺手种魔法豆"
                need_plant = True
        else:
            tier_eff = "skip"
            badge_txt = "✅ 不用种魔法豆"
            need_plant = False
        dist = None
        if player_pos:
            px, py, pz = player_pos
            sx, sy, sz = sp["pos"]
            if abs(sy - py) <= 10.0:
                d_xz = ((sx - px) ** 2 + (sz - pz) ** 2) ** 0.5
                if d_xz <= 20.0:
                    dist = round(d_xz, 1)
        out.append({
            "loc": sp["loc"],
            "name": sp["name"],
            "skull_id": sp["skull_id"],
            "tier": tier_eff,
            "badge": badge_txt,
            "why": sp["why"],
            "need_plant": need_plant,
            "planted": planted,
            "dist": dist,
            "pos": sp["pos"],
        })
    return out


@dataclass
class RegionReport:
    location: str
    name_zh: str
    skull_total: int
    skull_got: int
    skull_reachable_missing: list[EvaluatedItem]
    skull_unreachable: list[EvaluatedItem]
    skull_collected: list[EvaluatedItem]
    hp_total: int
    hp_got: int
    hp_reachable_missing: list[EvaluatedItem]
    hp_unreachable: list[EvaluatedItem]
    hp_collected: list[EvaluatedItem]
    quest_reachable_missing: list[EvaluatedItem]
    quest_unreachable: list[EvaluatedItem]
    quest_collected: list[EvaluatedItem]

    @property
    def reachable_missing_count(self) -> int:
        return len(self.skull_reachable_missing) + len(self.hp_reachable_missing) + len(self.quest_reachable_missing)

    @property
    def unreachable_count(self) -> int:
        return len(self.skull_unreachable) + len(self.hp_unreachable) + len(self.quest_unreachable)

    @property
    def total_items(self) -> int:
        return self.skull_total + self.hp_total + len(self.quest_reachable_missing) + len(self.quest_unreachable) + len(self.quest_collected)


@dataclass
class TrackerAlert:
    level: str  # info | good | warn
    title: str
    detail: str


class TrackerEngine:
    def __init__(self, db: dict[str, Any]):
        self.db = db
        self.cap_hashes: dict[str, int] = db["cap_hashes"]
        self.prev_location: str | None = None
        self.prev_collected_ids: set[str] | None = None
        self.prev_slot_name: str | None = None
        self.prev_source: str | None = None
        self.prev_snapshot: dict[str, Any] | None = None
        self._saw_loading: bool = False
        self.prev_chain_steps: dict[str, str] | None = None
        self.announced_chain_roadmap: set[str] = set()
        self.active_nearby_keys: set[str] = set()
        self.unlocked_boss_ids: set[str] = set()
        self.unlocked_tip_locs: set[str] = set()

    def _b(self, kv: dict[int, int], key: str) -> bool:
        h = self.cap_hashes.get(key)
        return bool(kv.get(h, 0)) if h else False

    def _i(self, kv: dict[int, int], key: str) -> int:
        h = self.cap_hashes.get(key)
        return int(kv.get(h, 0)) if h else 0

    def extract_caps(self, state: dict[str, Any]) -> dict[str, Any]:
        kv = state["kv32"]
        is_child = self._b(kv, "Sequence_IsChildhood")
        tokens = self._i(kv, "PouchData.Item_Token_Gold.StockNum")
        # Fallback to active b64 skull count if StockNum is 0
        b64 = state["b64"]
        b64_skulls = sum(1 for s in self.db["skulltulas"] if s["flag_key"] in b64)
        tokens = max(tokens, b64_skulls)

        has_hook = self._b(kv, "IsGet.Item_Hookshot") or self._b(kv, "IsGet.Item_Longshot")
        has_long = self._b(kv, "IsGet.Item_Longshot")
        has_bomb = self._b(kv, "IsGet.Item_Bomb") or self._b(kv, "IsGet.Item_BombBag_Small")
        has_ocarina = self._b(kv, "IsGet.Item_Ocarina_Fairy") or self._b(kv, "IsGet.Item_Ocarina_Time")
        empty_bottle_hash = 0xBE69DE49
        bottle_slots = [
            "PlayerStatus.AssignableItem.BottleInfo.BottleA.BottleItem",
            "PlayerStatus.AssignableItem.BottleInfo.BottleB.BottleItem",
            "PlayerStatus.AssignableItem.BottleInfo.BottleC.BottleItem",
            "PlayerStatus.AssignableItem.BottleInfo.BottleD.BottleItem",
        ]
        bottles_from_slots = sum(
            1 for k in bottle_slots
            if (h := self.cap_hashes.get(k)) and kv.get(h, empty_bottle_hash) not in (0, empty_bottle_hash)
        )
        bottles_from_flags = sum(
            1 for cond in [
                self._b(kv, "IsGet.Item_Bottle") or self._b(kv, "MiniGame_CatchCucco_IsCompleted"),
                self._b(kv, "IsGet.Item_Bottle_Milk") or self._b(kv, "IsClear_Minigame_FindOutCucco"),
                self._b(kv, "IsGet.Item_Bottle_Letter"),
                self._i(kv, "GhostShop_CouponNum") >= 10,
            ] if cond
        )
        bottles_count = max(bottles_from_slots, bottles_from_flags)
        has_bottle = bottles_count > 0 or self._b(kv, "IsGet.Item_Bottle") or self._b(kv, "IsGet.Item_Bottle_Milk") or self._b(kv, "IsGet.Item_Bottle_Letter")
        has_magic = self._i(kv, "PlayerStatus.MPMax") > 0
        has_epona = self._b(kv, "IsGet.Item_Melody_EponaSong")
        epona_enum_h = self.cap_hashes.get("Get_Epona_State_Enum")
        won_epona = (
            self._b(kv, "Get_Epona_AfterWonGambleRaceAndBeforeTalonBacked")
            or self._b(kv, "HaveTalked_Special.Get_Epona_AfterEscapeFromLonLonRanch_Npc_Hylia_Ingo_002_Adult_Talk_Event298")
            or self._b(kv, "HaveTalked_Special.Get_Epona_AfterWonGambleRace_Npc_Hylia_Malon_Adult_Talk_Event327")
            or self._b(kv, "NaviChat_Cancel_HorseRaceClear")
            or self._b(kv, "MiniGame_Unlock_HorseRace")
            or (bool(epona_enum_h) and kv.get(epona_enum_h) == 0x4C0A63F4)
        )
        has_requiem = has_ocarina and self._b(kv, "IsGet.Item_Melody_SpiritRequiem")
        has_gerudo_card = self._b(kv, "IsGet.Item_Token_Gerudo")
        can_cross_gerudo_bridge = (not is_child) and (won_epona or has_long)
        zora_fountain_child = self._b(kv, "HavePlayedEvent.Dm_ZoraFountain_0000") or self._b(kv, "IsGet.Item_Stone_Water")

        has_magic_bean = self._b(kv, "IsGet.Item_MagicBean")
        caps = {
            "is_child": is_child,
            "child": is_child,
            "adult": not is_child,
            "sword": self._b(kv, "IsGet.Weapon_Sword_Kokiri") or self._b(kv, "IsGet.Weapon_Sword_Master") or self._b(kv, "IsGet.Weapon_Sword_Biggoron"),
            "deku_stick": True,  # Always obtainable from Deku Babas/shops
            "slingshot": self._b(kv, "IsGet.Weapon_Range_SlingShot"),
            "boomerang": self._b(kv, "IsGet.Item_Boomerang"),
            "bomb": has_bomb,
            "hammer": self._b(kv, "IsGet.Item_Hammer"),
            "bow": self._b(kv, "IsGet.Weapon_Range_Bow"),
            "hookshot": has_hook,
            "longshot": has_long,
            "iron_boots": self._b(kv, "IsGet.Armor_Adult_HeavyBoot"),
            "hover_boots": self._b(kv, "IsGet.Armor_Adult_HoverBoot"),
            "goron_bracelet": self._b(kv, "IsGet.Armor_Child_Gauntlet_Goron") or self._b(kv, "IsGet.Armor_Adult_Gauntlet_Silver") or self._b(kv, "IsGet.Armor_Adult_Gauntlet_Gold"),
            "silver_gauntlets": self._b(kv, "IsGet.Armor_Adult_Gauntlet_Silver") or self._b(kv, "IsGet.Armor_Adult_Gauntlet_Gold"),
            "golden_gauntlets": self._b(kv, "IsGet.Armor_Adult_Gauntlet_Gold"),
            "bottle": has_bottle,
            "magic": has_magic,
            "dins_fire": has_magic and self._b(kv, "IsGet.Item_DinFire"),
            "fire_arrow": has_magic and self._b(kv, "IsGet.Weapon_Range_Bow") and self._b(kv, "IsGet.Item_Arrow_Fire"),
            "ocarina": has_ocarina,
            "zelda_lullaby": has_ocarina and self._b(kv, "IsGet.Item_Melody_ZeldaLullaby"),
            "lullaby": has_ocarina and self._b(kv, "IsGet.Item_Melody_ZeldaLullaby"),
            "epona": has_ocarina and has_epona,
            "epona_adult": (not is_child) and won_epona,
            "saria": has_ocarina and self._b(kv, "IsGet.Item_Melody_SariaSong"),
            "sun_song": has_ocarina and self._b(kv, "IsGet.Item_Melody_SunSong"),
            "song_of_time": has_ocarina and self._b(kv, "IsGet.Item_Melody_TimeSong"),
            "storm_song": has_ocarina and self._b(kv, "IsGet.Item_Melody_StormSong"),
            "minuet": has_ocarina and self._b(kv, "IsGet.Item_Melody_ForestMinuet"),
            "bolero": has_ocarina and self._b(kv, "IsGet.Item_Melody_FireBolero"),
            "serenade": has_ocarina and self._b(kv, "IsGet.Item_Melody_WaterSerenade"),
            "requiem": has_requiem,
            "nocturne": has_ocarina and self._b(kv, "IsGet.Item_Melody_ShadowNocturne"),
            "scarecrow": has_ocarina and self._b(kv, "IsGet.Item_Melody_ScarecrowSong"),
            "scarecrow_longshot": has_ocarina and self._b(kv, "IsGet.Item_Melody_ScarecrowSong") and has_long,
            "zora_tunic": self._b(kv, "IsGet.Armor_Adult_Zora"),
            "goron_tunic": self._b(kv, "IsGet.Armor_Adult_Goron"),
            "silver_scale": self._b(kv, "IsGet.Item_Scale_Silver") or self._b(kv, "IsGet.Item_Scale_Gold"),
            "gold_scale": self._b(kv, "IsGet.Item_Scale_Gold"),
            "magic_bean": has_magic_bean,
            "bean_lw01": self._b(kv, "Gimmick_MagicBeanSoil_LostWood01") or (is_child and has_magic_bean),
            "bean_lh": self._b(kv, "Gimmick_MagicBeanSoil_LakeHylia") or (is_child and has_magic_bean),
            "bean_gy": self._b(kv, "Gimmick_MagicBeanSoil_Graveyard") or (is_child and has_magic_bean),
            "bean_dmt": self._b(kv, "Gimmick_MagicBeanSoil_DeathMountainTrail") or (is_child and has_magic_bean),
            "bean_dmc": self._b(kv, "Gimmick_MagicBeanSoil_DeathMountainCrater") or (is_child and has_magic_bean),
            "bean_dc": self._b(kv, "Gimmick_MagicBeanSoil_DesertColossus") or (is_child and has_magic_bean),
            "zelda_letter": self._b(kv, "IsGet.Item_ZeldaLetter") or self._b(kv, "IsGet.Item_Melody_ZeldaLullaby"),
            "gerudo_card": has_gerudo_card,
            "gerudo_bridge": can_cross_gerudo_bridge,
            "desert_access": has_requiem or (not is_child and has_gerudo_card and can_cross_gerudo_bridge),
            "zora_fountain_child": zora_fountain_child,
            "water_medal": self._b(kv, "IsGet.Item_Medal_Water"),
            "mask_keaton": self._b(kv, "IsGet.Armor_Child_Mask_Keaton"),
            "mask_skull": self._b(kv, "IsGet.Armor_Child_Mask_Skull"),
            "mask_truth": self._b(kv, "IsGet.Armor_Child_Mask_Truth"),
            "lens_truth": self._b(kv, "IsGet.Armor_GlassTruth"),
            "tokens_10": tokens >= 10,
            "tokens_20": tokens >= 20,
            "tokens_30": tokens >= 30,
            "tokens_40": tokens >= 40,
            "tokens_50": tokens >= 50,
            "note07_password": self._b(kv, "HaveReadHrlField_Note07"),
            "note12_spider_cleared": self._b(kv, "HaveReadHrlField_Note12_Enemy") or self._b(kv, "HaveReadHrlField_Note12_3"),
            "_tokens": tokens,
            "_life": self._i(kv, "PlayerStatus.Life"),
            "_max_life": self._i(kv, "PlayerStatus.MaxLife"),
            "_hp_quarter": self._i(kv, "PouchData.Obj_Heart_Piece.StockNum"),
            "_rupees": self._i(kv, "PlayerStatus.CurrentRupee"),
            "_songs_count": sum(
                1 for k in [
                    "IsGet.Item_Melody_ZeldaLullaby", "IsGet.Item_Melody_EponaSong",
                    "IsGet.Item_Melody_SariaSong", "IsGet.Item_Melody_SunSong",
                    "IsGet.Item_Melody_TimeSong", "IsGet.Item_Melody_StormSong",
                    "IsGet.Item_Melody_ForestMinuet", "IsGet.Item_Melody_FireBolero",
                    "IsGet.Item_Melody_WaterSerenade", "IsGet.Item_Melody_SpiritRequiem",
                    "IsGet.Item_Melody_ShadowNocturne", "IsGet.Item_Melody_LightPrelude",
                ] if self._b(kv, k)
            ),
            "_stones_count": max(
                self._i(kv, "DoorOfTime_GetStoneCount"),
                sum(1 for k in ["IsGet.Item_Stone_Forest", "IsGet.Item_Stone_Fire", "IsGet.Item_Stone_Water"] if self._b(kv, k)),
            ),
            "_medals_count": sum(
                1 for k in [
                    "IsGet.Item_Medal_Light", "IsGet.Item_Medal_Forest", "IsGet.Item_Medal_Fire",
                    "IsGet.Item_Medal_Water", "IsGet.Item_Medal_Shadow", "IsGet.Item_Medal_Spirit",
                ] if self._b(kv, k)
            ),
            "_bottles_count": bottles_count,
        }
        return caps

    def _is_collected(self, item: dict[str, Any], state: dict[str, Any]) -> bool:
        if item["id"] == "q_llr_epona_adult":
            epona_enum_h = self.cap_hashes.get("Get_Epona_State_Enum")
            if epona_enum_h and state["kv32"].get(epona_enum_h) == 0x4C0A63F4:
                return True
        ft = item["flag_type"]
        fk = item["flag_key"]
        if fk is None:
            return False
        if ft == "b64":
            return fk in state["b64"]
        if ft == "bool":
            return bool(state["kv32"].get(fk, 0))
        if ft == "any_bool":
            return any(bool(state["kv32"].get(h, 0)) for h in fk)
        if ft == "int_ge":
            h, thr = fk
            return int(state["kv32"].get(h, 0)) >= thr
        return False

    def _check_reachability(self, era: str, reqs: list[str], caps: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
        missing: list[str] = []
        guides: list[str] = []
        if era == "child" and not caps["child"]:
            missing.append("幼年形态")
            guides.append(CAP_HOW_TO_GET_ZH["child"])
        elif era == "adult" and not caps["adult"]:
            missing.append("成年形态")
            guides.append(CAP_HOW_TO_GET_ZH["adult"])

        for clause in reqs:
            alts = clause.split("|")
            if any(caps.get(a, False) for a in alts):
                continue
            label = " 或 ".join(CAP_LABELS_ZH.get(a, a) for a in alts)
            missing.append(label)
            g = " / ".join(CAP_HOW_TO_GET_ZH[a] for a in alts if a in CAP_HOW_TO_GET_ZH)
            if g:
                guides.append(f"{label}：{g}")

        return (len(missing) == 0), missing, guides

    def evaluate(self, state: dict[str, Any]) -> dict[str, Any]:
        caps = self.extract_caps(state)
        all_items: list[EvaluatedItem] = []

        for lst in (self.db["skulltulas"], self.db["heart_pieces"], self.db["quests"]):
            for raw in lst:
                got = self._is_collected(raw, state)
                reach, missing, guides = self._check_reachability(raw["era"], raw["reqs"], caps)
                all_items.append(
                    EvaluatedItem(
                        id=raw["id"],
                        kind=raw["kind"],
                        location=raw["location"],
                        name=raw["name"],
                        era=raw["era"],
                        night_only=raw.get("night_only", False),
                        collected=got,
                        reachable=reach,
                        missing_reqs=missing,
                        missing_guides=guides,
                        guide=raw.get("guide", ""),
                        floor=raw.get("floor", ""),
                    )
                )

        regions: dict[str, RegionReport] = {}
        for loc in self.db["location_order"]:
            items = [x for x in all_items if x.location == loc]
            sk = [x for x in items if x.kind == "skulltula"]
            hp = [x for x in items if x.kind == "heart_piece"]
            qs = [x for x in items if x.kind == "quest"]
            regions[loc] = RegionReport(
                location=loc,
                name_zh=self.db["locations"].get(loc, loc),
                skull_total=len(sk),
                skull_got=sum(1 for x in sk if x.collected),
                skull_reachable_missing=[x for x in sk if not x.collected and x.reachable],
                skull_unreachable=[x for x in sk if not x.collected and not x.reachable],
                skull_collected=[x for x in sk if x.collected],
                hp_total=len(hp),
                hp_got=sum(1 for x in hp if x.collected),
                hp_reachable_missing=[x for x in hp if not x.collected and x.reachable],
                hp_unreachable=[x for x in hp if not x.collected and not x.reachable],
                hp_collected=[x for x in hp if x.collected],
                quest_reachable_missing=[x for x in qs if not x.collected and x.reachable],
                quest_unreachable=[x for x in qs if not x.collected and not x.reachable],
                quest_collected=[x for x in qs if x.collected],
            )

        total_skulls_got = max(caps["_tokens"], sum(1 for x in all_items if x.kind == "skulltula" and x.collected))
        total_hp_got = sum(1 for x in all_items if x.kind == "heart_piece" and x.collected)
        # Reconcile total_hp_got with MaxLife if MaxLife implies more/exact
        # Base 12 quarter-hearts + 4*containers + hp_got
        collected_ids = {x.id for x in all_items if x.collected}

        raw_loc = state.get("location")
        curr_loc = raw_loc
        if curr_loc == "IngoRanch":
            curr_loc = "LonLonRanch"
        elif curr_loc in ("CrumblingGanonCastle", "FinalBattleField"):
            curr_loc = "GanonCastle"
        elif curr_loc == "SageRoom":
            curr_loc = "TimeTemple"
        if curr_loc not in regions:
            curr_loc = "HyruleField"

        is_loading = bool(state.get("is_loading")) or raw_loc == "Title" or caps["_max_life"] < 12
        slot_name = state.get("slot_name", "slot_00")
        source = state.get("source", "save_file")

        alerts = self._compute_alerts(
            curr_loc,
            collected_ids,
            regions,
            total_skulls_got,
            total_hp_got,
            all_items,
            slot_name=slot_name,
            source=source,
            is_loading=is_loading,
        )
        story = compute_story_tracker(caps, state["kv32"], self.cap_hashes, curr_loc)
        if curr_loc == "LostWood" and story.get("target_loc") in ("SacredForestMeadow", "ForestTemple"):
            rg_sfm = get_lostwood_room_guidance(state.get("player_pos"), target="sfm")
            if rg_sfm:
                story["how_to"] = f"{rg_sfm}。{story['how_to']}"
        DUNGEON_LOCS = {
            "InsideTheDekuTree", "DodongoCavern", "InsideJabuJabuBelly",
            "BottomOfTheWell", "ForestTemple", "FireTemple",
            "IceCavern", "WaterTemple", "ShadowTemple", "SpiritTemple", "InsideGanonCastle",
        }
        droom_h = self.cap_hashes.get("DungeonRoom")
        droom = int(state["kv32"].get(droom_h, -1)) if (droom_h and curr_loc in DUNGEON_LOCS and droom_h in state["kv32"]) else None
        if droom is not None and droom < 0:
            droom = None
        active_chains = compute_active_chains(caps, state["kv32"], self.cap_hashes, curr_loc, self.db["locations"], player_pos=state.get("player_pos"))
        nearby_hints = compute_nearby_hints(curr_loc, state.get("player_pos"), all_items, self.db, dungeon_room=droom)
        bean_soil_tips = compute_bean_soil_tips(curr_loc, caps, state["kv32"], self.cap_hashes, collected_ids, player_pos=state.get("player_pos"))
        if caps["is_child"]:
            for bt in bean_soil_tips:
                if bt["dist"] is not None and not bt["planted"] and bt["skull_id"] in collected_ids:
                    nearby_hints.append({
                        "key": f"bean_soil:{bt['loc']}:{bt['name']}",
                        "kind": "bean_soil",
                        "dist": bt["dist"],
                        "dy": 0.0,
                        "compass": "",
                        "elev": "",
                        "radar": bt["badge"],
                        "name": f"{bt['name']}：{bt['badge']}",
                        "reachable": True,
                        "missing_reqs": [],
                        "guide": bt["why"],
                        "night_only": False,
                        "floor": "",
                        "is_grotto": False,
                        "need_plant": bt["need_plant"],
                        "tier": bt["tier"],
                    })
        if not is_loading:
            cur_chain_map = {c["id"]: c["step_key"] for c in active_chains}
            is_reload_msg = any("已同步读档进度" in a.title for a in alerts)
            if is_reload_msg:
                self.prev_chain_steps = cur_chain_map
                self.active_nearby_keys = {nh["key"] for nh in nearby_hints}
                for c in active_chains:
                    if c["timed"]:
                        alerts.append(
                            TrackerAlert(
                                "warn",
                                f"⏳ 限时跑腿进行中！立刻去【{c['target_zh']}】",
                                f"{c['header']}：{c['title']}｜{c['detail']}",
                            )
                        )
            else:
                prev_map = self.prev_chain_steps or {}
                for c in active_chains:
                    first_time_chain = (c["id"] not in self.announced_chain_roadmap)
                    step_changed = (prev_map.get(c["id"]) != c["step_key"])
                    if first_time_chain or step_changed:
                        self.announced_chain_roadmap.add(c["id"])
                        if c["timed"]:
                            ttl = f"⏳ 限时开始！立刻前往【{c['target_zh']}】"
                            lvl = "warn"
                        elif first_time_chain:
                            ttl = f"{c['badge']} 已开启多轮支线：{c['header']} → 去【{c['target_zh']}】"
                            lvl = "good"
                        else:
                            ttl = f"{c['badge']} {c['header']} → 下一步去【{c['target_zh']}】"
                            lvl = "good"
                        det = f"{c['title']}｜{c['detail']}"
                        if first_time_chain and c.get("roadmap"):
                            det += f"\n【完整多轮路线】{c['roadmap']}"
                        alerts.append(TrackerAlert(lvl, ttl, det))
                self.prev_chain_steps = cur_chain_map

                # Proximity / Stone of Agony popup when entering ~22m range of an uncollected item or grotto
                cur_near_keys = {nh["key"] for nh in nearby_hints}
                for nh in nearby_hints:
                    if nh["key"] not in self.active_nearby_keys:
                        if nh["kind"] == "bean_soil":
                            lvl = "warn" if nh.get("tier") == "must" else "info"
                            alerts.append(
                                TrackerAlert(
                                    lvl,
                                    f"🌱 附近软土坑（{nh['dist']}m）：{nh['name']}",
                                    nh["guide"],
                                )
                            )
                        elif nh["kind"] == "grotto":
                            alerts.append(
                                TrackerAlert(
                                    "info",
                                    f"🔔 附近响音石隐藏洞（{nh['dist']}m）",
                                    f"{nh['name']}｜{nh['guide']}",
                                )
                            )
                        elif nh["reachable"]:
                            kzh = "黄金骷髅蜘蛛" if nh["kind"] == "skulltula" else ("心之碎片" if nh["kind"] == "heart_piece" else "支线目标")
                            nt = "🌙仅限夜晚！" if nh["night_only"] else ""
                            fl_tag = f"[{nh['floor']}]" if nh.get("floor") else ""
                            r_part = f"🧭{nh['radar']}｜" if nh.get("radar") else ""
                            g_part = f"｜获取：{nh['guide']}" if nh.get("guide") else ""
                            alerts.append(
                                TrackerAlert(
                                    "info",
                                    f"🔔 附近发现可拿{fl_tag}{kzh}（水平{nh['dist']}m）{nt}",
                                    f"{r_part}{nh['name']}{g_part}",
                                )
                            )
                        else:
                            kzh = "黄金骷髅蜘蛛" if nh["kind"] == "skulltula" else ("心之碎片" if nh["kind"] == "heart_piece" else "支线目标")
                            reqs = "、".join(nh["missing_reqs"]) if nh["missing_reqs"] else "前置条件"
                            fl_tag = f"[{nh['floor']}]" if nh.get("floor") else ""
                            r_part = f"🧭{nh['radar']}｜" if nh.get("radar") else ""
                            g_part = f"｜做法：{nh['guide']}" if nh.get("guide") else ""
                            alerts.append(
                                TrackerAlert(
                                    "warn",
                                    f"🔒 附近{fl_tag}{kzh}【当前无法获得】（水平{nh['dist']}m）",
                                    f"{r_part}{nh['name']}｜缺前置：{reqs}{g_part}",
                                )
                            )
                self.active_nearby_keys = cur_near_keys
        region_boss_tips = BOSS_AND_MECHANIC_TIPS.get(curr_loc, [])
        active_boss = detect_active_boss(
            curr_loc,
            state["kv32"],
            self.cap_hashes,
            state.get("player_pos"),
            dungeon_room=droom,
        )
        boss_journal = evaluate_boss_journal(
            curr_loc,
            story,
            active_boss,
            state["kv32"],
            self.cap_hashes,
            self.unlocked_boss_ids,
            self.unlocked_tip_locs,
        )
        adjacent_miss = get_adjacent_reachable_items(curr_loc, all_items)

        return {
            "source": state["source"],
            "slot_name": state.get("slot_name", "slot_00"),
            "location": curr_loc,
            "location_zh": self.db["locations"].get(curr_loc, curr_loc),
            "caps": caps,
            "regions": regions,
            "all_items": all_items,
            "total_skulls_got": total_skulls_got,
            "total_skulls": 100,
            "total_hp_got": total_hp_got,
            "total_hp": 36,
            "alerts": alerts,
            "is_loading": is_loading,
            "story": story,
            "active_chains": active_chains,
            "nearby_hints": nearby_hints,
            "bean_soil_tips": bean_soil_tips,
            "get_bean_tips": lambda l: compute_bean_soil_tips(l, caps, state["kv32"], self.cap_hashes, collected_ids, player_pos=state.get("player_pos") if l == curr_loc else None),
            "region_boss_tips": region_boss_tips,
            "all_boss_tips": BOSS_AND_MECHANIC_TIPS,
            "active_boss": active_boss,
            "boss_journal": boss_journal,
            "adjacent_miss": adjacent_miss,
            "get_adjacent": lambda l: get_adjacent_reachable_items(l, all_items),
        }

    def _compute_alerts(
        self,
        curr_loc: str,
        collected_ids: set[str],
        regions: dict[str, RegionReport],
        total_skulls: int,
        total_hp: int,
        all_items: list[EvaluatedItem],
        slot_name: str = "slot_00",
        source: str = "save_file",
        is_loading: bool = False,
    ) -> list[TrackerAlert]:
        alerts: list[TrackerAlert] = []
        by_id = {x.id: x for x in all_items}

        # Title screen / loading transition: never pollute baseline with transient empty flags
        if is_loading:
            if self.prev_collected_ids is not None:
                self._saw_loading = True
            return alerts

        # First tick: initialize baseline without false alerts
        if self.prev_location is None or self.prev_collected_ids is None:
            self.prev_location = curr_loc
            self.prev_collected_ids = set(collected_ids)
            self.prev_slot_name = slot_name
            self.prev_source = source
            reg = regions[curr_loc]
            alerts.append(
                TrackerAlert(
                    "info",
                    f"已定位当前区域：{reg.name_zh}",
                    f"本区蜘蛛 {reg.skull_got}/{reg.skull_total}、心之碎片 {reg.hp_got}/{reg.hp_total}，当前可补 {reg.reachable_missing_count} 项。",
                )
            )
            return alerts

        newly_got = collected_ids - self.prev_collected_ids
        newly_lost = self.prev_collected_ids - collected_ids
        slot_changed = (
            source == "save_file"
            and self.prev_source == "save_file"
            and self.prev_slot_name is not None
            and slot_name != self.prev_slot_name
        )
        source_jump = (
            self.prev_source is not None
            and source != self.prev_source
            and (len(newly_got) >= 3 or len(newly_lost) >= 1)
        )
        reload_jump = (
            self._saw_loading
            or bool(newly_lost)
            or len(newly_got) >= 4
            or (curr_loc != self.prev_location and len(newly_got) >= 3)
        )
        self._saw_loading = False
        if slot_changed or source_jump or reload_jump:
            self.prev_location = curr_loc
            self.prev_collected_ids = set(collected_ids)
            self.prev_slot_name = slot_name
            self.prev_source = source
            self.unlocked_boss_ids.clear()
            self.unlocked_tip_locs.clear()
            reg = regions[curr_loc]
            alerts.append(
                TrackerAlert(
                    "info",
                    f"🔄 已同步读档进度（{reg.name_zh}）",
                    f"黄金骷髅蜘蛛 {total_skulls}/100 · 心之碎片 {total_hp}/36（本区当前可补 {reg.reachable_missing_count} 项，已屏蔽读档批量弹窗）",
                )
            )
            return alerts

        # 1. Newly collected items
        for cid in sorted(newly_got):
            it = by_id.get(cid)
            if not it:
                continue
            reg = regions[it.location]
            if it.kind == "skulltula":
                rem_global = max(0, 100 - total_skulls)
                rem_local_reach = len(reg.skull_reachable_missing)
                alerts.append(
                    TrackerAlert(
                        "good",
                        f"🕷 已收集 1 只黄金骷髅蜘蛛！（{reg.name_zh} · {it.name}）",
                        f"本区 {reg.skull_got}/{reg.skull_total}（当前可拿还缺 {rem_local_reach} 只）｜全图 {total_skulls}/100（还缺 {rem_global} 只）",
                    )
                )
            elif it.kind == "heart_piece":
                rem_local_reach = len(reg.hp_reachable_missing)
                alerts.append(
                    TrackerAlert(
                        "good",
                        f"❤ 已收集 1 块心之碎片！（{reg.name_zh} · {it.name}）",
                        f"本区 {reg.hp_got}/{reg.hp_total}（当前可拿还缺 {rem_local_reach} 块）｜全图 {total_hp}/36（还剩 {max(0, 36 - total_hp)} 块）",
                    )
                )
            elif it.kind == "quest":
                rem_q = len(reg.quest_reachable_missing)
                alerts.append(
                    TrackerAlert(
                        "good",
                        f"⭐ 已完成支线/取得道具：{it.name}",
                        f"所在区域：{reg.name_zh}（本区可补支线还剩 {rem_q} 项）",
                    )
                )

        # 2. Region transition detection
        if curr_loc != self.prev_location:
            prev_reg = regions.get(self.prev_location)
            new_reg = regions[curr_loc]
            if prev_reg:
                missed = (
                    prev_reg.skull_reachable_missing
                    + prev_reg.hp_reachable_missing
                    + prev_reg.quest_reachable_missing
                )
                if missed:
                    preview = "；".join(
                        f"[{'蜘蛛' if m.kind=='skulltula' else ('心片' if m.kind=='heart_piece' else '支线')}] {m.name}"
                        for m in missed[:4]
                    )
                    more = f" 等共 {len(missed)} 项" if len(missed) > 4 else f"（共 {len(missed)} 项）"
                    alerts.append(
                        TrackerAlert(
                            "warn",
                            f"⚠ 离开【{prev_reg.name_zh}】漏项提醒！",
                            f"当前可拿却未收集{more}：{preview}",
                        )
                    )
                else:
                    unreach = len(prev_reg.skull_unreachable) + len(prev_reg.hp_unreachable) + len(prev_reg.quest_unreachable)
                    msg = f"当前可拿项已全部拿完" + (f"（另有 {unreach} 项暂缺前置已忽略）" if unreach else "")
                    alerts.append(TrackerAlert("info", f"✔ 已离开【{prev_reg.name_zh}】", msg))

            # Report newly entered region
            alerts.append(
                TrackerAlert(
                    "info",
                    f"📍 进入新区域：{new_reg.name_zh}",
                    f"蜘蛛 {new_reg.skull_got}/{new_reg.skull_total}（可拿还缺 {len(new_reg.skull_reachable_missing)}）· 心之碎片 {new_reg.hp_got}/{new_reg.hp_total}（可拿还缺 {len(new_reg.hp_reachable_missing)}）· 支线可补 {len(new_reg.quest_reachable_missing)} 项",
                )
            )

        self.prev_location = curr_loc
        self.prev_collected_ids = set(collected_ids)
        self.prev_slot_name = slot_name
        self.prev_source = source
        return alerts
