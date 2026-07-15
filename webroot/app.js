// 洛书 WebUI - 支持 Magisk / KernelSU / SukiSU
// v12.8 — MIUIX Layered UI

import { exec } from './kernelsu.js';

const MODULE_DIR = '/data/adb/modules/LuoShu';
const FONT_MANAGER = `${MODULE_DIR}/common/font_manager.sh`;
const DATA_CACHE_KEY = 'luoshu_font_data_v2';

const WEIGHT_LABELS = {
    thin: '极细', light: '细体', regular: '常规',
    medium: '中等', semibold: '半粗', bold: '粗体', black: '特粗', variable: '可变'
};

// 拼音数据 — 拼音首字母 → 汉字，覆盖常用汉字全音节
const PINYIN_MAP = (() => {
    const data = {
    'a':'阿啊锕嗄吖腌','ai':'爱艾挨哎碍癌矮埃哀蔼隘暧霭捱瑷','an':'安按暗岸案俺鞍黯氨谙胺庵铵揞犴埯','ang':'昂盎肮',
    'ao':'奥傲澳熬凹袄坳拗嗷螯鏊鳌翱','ba':'把八吧巴拔霸爸罢坝芭跋靶笆耙茇魃捌钯','bai':'百白败摆柏拜伯佰稗捭',
    'ban':'办半版般班板伴搬扮斑颁瓣拌扳绊阪坂','bang':'帮邦棒榜傍绑磅谤蚌浜膀镑','bao':'报包保暴薄宝爆饱抱褒堡苞雹豹曝瀑葆孢煲鸨',
    'bei':'被北备背悲碑辈杯贝倍卑蓓惫钡狈悖碚','ben':'本奔笨苯畚坌','beng':'蹦崩绷泵迸甏嘣甭','bi':'比必笔毕币避闭逼鼻彼壁臂碧蔽鄙弊庇璧泌弼匕荸薜哔陛',
    'bian':'变边便编辩遍鞭辨贬卞扁匾汴砭碥鳊','biao':'表标彪镖飙裱膘骠飚','bie':'别憋鳖瘪蹩','bin':'宾滨彬斌鬓缤濒槟摈膑',
    'bing':'并病兵冰饼丙柄秉炳禀邴摒','bo':'波播伯博薄驳玻剥脖搏拨帛舶箔铂柏勃菠钵擘亳','bu':'不部步布补捕卜埠怖哺簿埔卟逋',
    'ca':'擦嚓','cai':'才材财采彩猜蔡裁踩菜睬','can':'参残惨灿餐惭蚕璨粲孱','cang':'藏仓苍沧舱','cao':'草操曹槽嘈漕螬',
    'ce':'测策侧册厕恻','cen':'参岑涔','ceng':'曾层蹭','cha':'查差察茶插叉诧刹岔搽碴楂槎','chai':'差拆柴豺钗侪虿',
    'chan':'产阐缠铲蝉颤潺蟾婵谄忏孱廛澶','chang':'长常场唱昌肠偿厂畅倡尝猖敞怅裳嫦昶菖阊','chao':'超朝潮炒抄吵嘲巢晁焯怊',
    'che':'车彻撤尺扯澈掣坼','chen':'称陈晨沉衬趁臣尘辰郴嗔琛忱碜抻','cheng':'成城程称承诚呈乘撑惩秤骋瞠丞铛埕晟柽',
    'chi':'吃持迟尺赤池翅耻齿驰斥炽嗤痴弛侈啻敕笞叱','chong':'重冲充崇宠虫忡憧铳舂艟','chou':'抽愁仇丑筹酬绸瞅稠臭踌俦畴',
    'chu':'出处初除楚础触储畜厨橱雏矗搐锄滁躇黜','chuan':'穿传船川串喘椽氚钏舛遄','chuang':'创窗床闯疮幢怆',
    'chui':'吹垂炊锤捶陲槌','chun':'春纯唇醇蠢椿淳鹑蝽','chuo':'戳绰辍啜龊','ci':'此次词刺瓷磁慈辞雌茨祠疵呲鹚',
    'cong':'从丛聪葱匆囱淙琮璁','cou':'凑','cu':'促粗醋簇卒蹴蹙徂','cuan':'窜篡蹿撺爨','cui':'崔催翠脆摧粹萃璀瘁淬啐','cun':'村存寸',
    'cuo':'错措挫搓撮磋痤矬锉','da':'大打达答搭哒嗒沓鞑耷褡笪','dai':'大代带待袋戴呆歹贷逮怠殆黛怠迨傣',
    'dan':'但单弹胆淡蛋担丹旦诞郸掸惮眈疸','dang':'当党档荡挡宕砀铛裆凼','dao':'到道导倒刀岛盗稻悼蹈捣祷叨','de':'的地得德',
    'deng':'等灯登邓瞪凳蹬磴镫噔','di':'地第底低敌弟递帝堤笛滴迪抵涤缔嫡翟蒂坻荻嘀柢','dian':'点电店典惦垫滇殿甸奠巅碘佃癜阽',
    'diao':'调掉雕吊刁叼貂碉鲷铫','die':'爹跌叠蝶谍碟迭喋耋牒蹀','ding':'定订顶丁叮盯钉鼎锭町铤腚','diu':'丢',
    'dong':'动东冬懂洞董冻栋侗恫峒鸫岽','dou':'都斗抖豆逗兜陡痘窦蚪蔸','du':'都度读独杜渡毒赌堵肚妒镀睹督笃嘟渎牍',
    'duan':'断段短端锻缎煅椴','dui':'对队堆兑怼碓憝','dun':'吨顿盾蹲敦墩钝遁盹沌炖砘','duo':'多夺朵躲堕舵惰垛踱咄铎哆',
    'e':'恶额鹅俄饿扼遏愕噩萼厄呃婀轭腭','en':'恩','er':'而二儿尔耳迩洱贰饵铒鸸',
    'fa':'发法罚阀伐筏乏垡砝','fan':'反饭翻犯范烦凡泛帆藩番繁贩樊钒蕃梵幡燔','fang':'方放房防访仿芳妨纺坊肪邡舫枋',
    'fei':'非飞费肥废匪菲啡沸肺蜚妃斐诽翡霏扉腓痱','fen':'分份纷粉奋愤氛坟焚酚芬焚汾忿棼','feng':'风丰封峰疯锋蜂冯凤奉枫逢缝讽烽俸葑',
    'fo':'佛','fou':'否','fu':'夫服副父复福富附府负妇夫赴浮扶符腐傅伏抚辅覆肤付弗芙幅腹斧拂俘涪釜缚甫脯茯郛阜驸',
    'ga':'噶嘎尬轧伽','gai':'改该概盖钙丐溉赅垓陔','gan':'干感赶敢甘肝杆赣竿柑尴秆擀坩苷','gang':'刚钢岗港纲缸杠冈罡扛筻',
    'gao':'高搞告稿糕膏皋羔睾槔镐缟','ge':'个各歌格哥革隔戈葛阁割胳鸽搁疙咯屹嗝圪硌','gei':'给','gen':'跟根亘艮茛',
    'geng':'更耕庚梗羹哽赓埂绠','gong':'工公共供功攻宫恭拱贡弓巩躬汞蚣龚','gou':'够狗沟构购勾苟钩垢佝诟枸篝觏',
    'gu':'故古顾股鼓骨孤估姑固谷雇菇箍辜咕沽蛊汩锢牯','gua':'挂瓜刮寡卦呱剐','guai':'怪拐乖','guan':'关管官观馆冠惯灌贯棺纶掼鹳矜鳏',
    'guang':'光广逛胱咣犷桄','gui':'贵归鬼桂规柜龟硅轨诡跪闺瑰圭刽癸炔皈匦','gun':'滚棍辊衮绲','guo':'过国果郭锅裹帼椁蝈聒',
    'ha':'哈','hai':'还海害孩亥骇嗨氦醢','han':'汉含喊寒韩涵罕函翰撼旱捍酣憨瀚颔焊鼾顸邗菡撖','hang':'行航杭夯巷吭沆绗桁',
    'hao':'好号毫豪耗浩郝皓昊嚎壕灏蒿薅貉','he':'和合何河喝赫荷核盒贺禾鹤褐阖劾涸曷貉诃','hei':'黑嘿','hen':'很恨狠痕',
    'heng':'横恒衡哼亨珩蘅桁','hong':'红宏洪鸿虹轰弘哄烘泓蕻闳訇','hou':'后候厚侯猴喉吼逅篌骺糇',
    'hu':'护呼湖互户虎胡忽糊乎壶狐沪胡弧唬瑚斛惚浒祜琥鹄','hua':'画花化华话划滑桦哗骅砉铧猾','huai':'坏怀淮槐徊踝',
    'huan':'还环换欢缓患幻唤焕宦寰浣涣奂桓豢鬟郇','huang':'黄慌皇荒晃煌惶恍簧凰蝗璜徨潢','hui':'会回汇辉灰惠毁慧挥绘徽恢秽贿晦卉诲彗晖麾烩',
    'hun':'混婚魂浑昏荤馄诨阍','huo':'或活火伙货获祸霍惑豁伙和',
    'ji':'机几级计记技及基极己际集纪急既济继积击奇激迹绩吉辑籍姬疾饥肌藉棘矶讥祭缉棘蓟',
    'jia':'家加价假甲架佳驾嫁嘉夹稼颊钾枷茄荚葭郏','jian':'见间建件简坚健减渐剑检践鉴肩兼键碱剪捡箭监柬俭尖艰荐歼奸笺茧槛缄涧谏谫',
    'jiang':'将江讲降奖蒋疆浆僵匠酱姜桨绛缰豇礓','jiao':'教交角叫较脚焦觉浇郊娇骄娇矫搅狡缴酵饺剿椒蛟跤礁',
    'jie':'接结节解界介借姐揭杰洁届阶戒截竭街劫睫藉诫芥疖偈婕','jin':'进金今近仅紧尽禁津筋锦谨晋巾襟浸靳烬瑾衿缙',
    'jing':'经京精静景睛晶惊竟径境敬井竞净警镜靖荆兢颈菁泾旌','jiong':'窘迥炯扃炅','jiu':'就九久旧救酒纠究揪舅韭疚鸠赳臼',
    'ju':'具局举据句巨距聚拒俱剧居惧鞠拘菊驹矩沮锯踞掬飓','juan':'卷捐鹃娟倦眷绢隽涓镌','jue':'觉决绝角掘诀爵嚼倔崛獗厥蹶攫矍',
    'jun':'军均俊君峻菌竣钧骏浚隽','ka':'卡咖喀','kai':'开凯楷慨铠揩','kan':'看刊坎堪砍侃槛勘龛瞰','kang':'抗康扛慷炕亢糠伉',
    'kao':'考靠烤拷犒铐','ke':'可科客课颗克刻壳渴柯磕瞌坷恪氪珂','ken':'肯垦恳啃龈','keng':'坑吭铿','kong':'空控孔恐倥崆箜',
    'kou':'口扣寇叩蔻筘','ku':'苦哭库裤酷枯窟骷刳','kua':'夸跨垮挎胯侉','kuai':'快块筷会脍蒯侩','kuan':'款宽',
    'kuang':'况矿狂框旷匡筐眶诓诳邝','kui':'亏愧溃葵魁窥盔馈睽逵馗','kun':'困昆坤捆琨锟醌','kuo':'扩括阔廓',
    'la':'拉啦辣蜡腊喇垃剌旯砬','lai':'来赖莱睐癞籁徕','lan':'兰蓝栏拦烂览篮澜懒缆榄岚婪阑褴','lang':'浪狼朗郎廊琅螂榔啷',
    'lao':'老劳牢捞姥佬酪潦唠崂铹痨','le':'了乐勒','lei':'类泪雷累擂磊蕾肋儡镭垒耒酹','leng':'冷愣楞棱',
    'li':'力里理利立李离历例礼丽粒厉璃犁漓黎栗沥荔莉哩痢篱吏戾唳锂','lian':'连联练脸恋炼莲廉帘怜链涟镰敛琏裢',
    'liang':'两亮量凉良粮梁辆晾粱踉莨','liao':'了料聊疗僚寥撩潦燎撂獠镣','lie':'列烈裂猎劣冽趔洌',
    'lin':'林临邻淋琳霖凛磷鳞麟吝蔺嶙遴','ling':'领令另灵零龄凌玲陵铃菱伶羚岭绫聆囹','liu':'六流留刘柳溜硫瘤浏镏琉',
    'long':'龙隆笼拢聋珑窿陇泷','lou':'楼漏露陋娄搂篓镂','lu':'路陆录露鲁炉卢鹿庐芦颅禄麓泸碌掳辂',
    'lv':'绿率旅律铝吕侣屡缕履氯滤驴闾榈膂','lve':'略掠','luan':'乱卵峦鸾挛孪栾','lun':'论轮伦沦纶囵',
    'luo':'落罗裸骆络洛逻螺锣萝珞烙','ma':'吗妈马嘛麻骂码蚂蟆玛','mai':'买卖麦迈埋脉霾劢','man':'满慢漫蛮曼蔓瞒馒幔鳗',
    'mang':'忙盲芒茫莽氓邙硭','mao':'毛冒猫帽贸矛貌茅锚卯髦耄牦','me':'么','mei':'没美每妹媒梅枚眉酶霉煤玫镁媚寐楣莓',
    'men':'门们闷扪焖懑','meng':'梦猛蒙盟孟萌朦锰懵蜢勐','mi':'米密迷秘蜜觅弥泌眯靡谜糜醚幂咪','mian':'面棉免眠绵缅勉冕娩腼沔',
    'miao':'秒妙描苗庙瞄藐渺淼眇','mie':'灭蔑篾乜咩','min':'民敏闽闵皿泯珉岷','ming':'名明命鸣铭冥茗溟暝','miu':'谬',
    'mo':'没莫末模默磨魔墨摸沫漠摩抹寞陌蘑脉蓦','mou':'某谋牟眸缪哞','mu':'目母木亩幕牧墓慕穆暮拇牡沐睦募',
    'na':'那拿哪纳娜呐捺钠肭','nai':'乃奶耐奈氖艿鼐','nan':'男南难楠喃腩','nang':'囊','nao':'脑闹挠恼瑙呶','ne':'呢',
    'nei':'内','nen':'嫩','neng':'能','ni':'你尼泥逆拟腻妮霓昵溺倪怩铌','nian':'年念碾撵拈廿黏辇','niang':'娘酿',
    'niao':'鸟尿袅茑嬲','nie':'捏镍聂涅孽蹊嗫蹑','nin':'您','ning':'宁凝拧咛狞柠','niu':'牛扭纽钮拗妞狃',
    'nong':'农弄浓脓侬','nu':'努怒奴弩孥驽','nv':'女','nuan':'暖','nve':'虐','nuo':'诺挪懦糯娜搦','o':'哦',
    'ou':'欧偶殴鸥呕藕耦沤','pa':'怕爬帕趴琶葩耙筢','pai':'排派牌拍徘湃俳蒎','pan':'盘判盼叛攀畔潘磐蹒蟠',
    'pang':'旁胖庞乓膀彷滂','pao':'跑炮泡抛袍刨疱','pei':'配陪培赔佩沛裴胚霈辔','pen':'盆喷',
    'peng':'朋碰棚捧膨蓬鹏篷烹抨彭硼澎','pi':'批皮否匹脾疲辟僻劈屁啤琵痞癖坯譬霹丕砒罴','pian':'片便偏篇骗翩扁骈',
    'piao':'票飘漂瓢朴飘缥','pie':'撇瞥','pin':'品贫拼频聘姘嫔','ping':'平评瓶凭萍屏苹坪枰','po':'破迫颇婆坡泊魄粕',
    'pu':'普铺扑朴谱仆葡蒲瀑圃曝璞濮噗匍','qi':'起其七期气奇器齐企汽妻弃棋旗岂戚启骑契泣歧乞凄祈绮沏憩',
    'qia':'恰掐洽','qian':'前钱千签浅牵迁潜谦歉铅纤嵌乾遣阡芊茜黔','qiang':'强枪墙抢腔呛锵跄羌蔷戕',
    'qiao':'桥巧悄瞧敲乔翘壳雀撬锹跷峭','qie':'切且窃妾怯茄','qin':'亲秦琴勤芹沁寝禽擒覃',
    'qing':'情请清青轻庆晴倾卿擎氢顷磬罄','qiong':'穷琼穹邛茕','qiu':'球求秋丘邱囚酋裘虬鳅','qu':'去取区曲趣渠屈驱娶趋衢蛐觑',
    'quan':'全权圈劝泉拳犬券醛蜷诠','que':'却确缺雀瘸鹊榷阙','qun':'群裙','ran':'然燃染冉髯','rang':'让壤嚷瓤穰',
    'rao':'绕饶扰娆桡','re':'热惹','ren':'人任认忍仁韧刃纫荏仞稔','reng':'仍扔','ri':'日',
    'rong':'容荣融溶蓉绒熔戎榕茸冗嵘','rou':'肉柔揉蹂鞣','ru':'如入乳儒辱汝茹褥孺濡蠕','ruan':'软阮','rui':'瑞锐蕊芮睿',
    'run':'润闰','ruo':'若弱','sa':'撒洒萨飒卅','sai':'赛塞腮噻','san':'三散伞叁馓','sang':'桑丧嗓','sao':'扫嫂臊骚',
    'se':'色涩瑟啬穑','sen':'森','seng':'僧','sha':'沙杀啥傻厦刹砂莎鲨煞纱霎痧','shai':'晒筛',
    'shan':'山善闪衫陕扇删珊杉擅煽','shang':'上商尚伤赏裳殇','shao':'少绍烧稍勺韶哨邵捎芍',
    'she':'社设射涉舍蛇奢舌赦摄佘麝','shen':'什深神审申伸身沈甚慎渗绅肾呻','sheng':'生声省胜升盛圣牲绳笙甥',
    'shi':'是时十事市实使世示式识石师史始士施食室势视试适失释湿拾饰诗狮逝矢侍氏仕恃','shou':'手受收首守授寿售瘦狩兽',
    'shu':'书数术树属输述熟束署舒殊蔬鼠疏竖淑蜀黍暑','shua':'刷耍','shuai':'帅衰摔甩','shuan':'栓拴闩涮',
    'shuang':'双爽霜孀','shui':'水谁睡税','shun':'顺瞬舜吮','shuo':'说硕烁朔铄槊','si':'四思死丝司似斯私撕嗣嘶伺肆',
    'song':'送松宋颂耸诵淞崧','sou':'搜艘擞嗽叟','su':'苏速素诉塑肃宿俗酥粟溯夙','suan':'算酸蒜',
    'sui':'随岁虽碎遂隋髓绥祟邃','sun':'孙损笋荪隼','suo':'所缩锁索梭琐蓑','ta':'他她它踏塔榻',
    'tai':'太台态泰抬胎汰钛苔肽','tan':'谈弹探坦叹滩贪摊碳毯潭谭檀覃','tang':'堂唐躺糖趟塘汤倘棠膛烫',
    'tao':'讨套逃桃淘陶萄涛掏滔韬','te':'特','teng':'腾疼藤誊','ti':'提题体替踢梯剔蹄啼屉涕',
    'tian':'天田填甜添恬舔腆','tiao':'条调跳挑眺迢粜','tie':'铁贴帖','ting':'听停庭厅挺亭婷廷烃霆',
    'tong':'同通统痛铜童筒桶彤桐瞳佟','tou':'头投透偷','tu':'土突图途涂屠兔秃凸荼','tuan':'团湍',
    'tui':'推退腿褪颓','tun':'吞屯臀','tuo':'脱拖托妥拓陀驼椭唾','wa':'瓦挖娃洼袜蛙佤娲','wai':'外歪',
    'wan':'万完晚玩湾碗腕弯挽顽宛婉丸','wang':'王望网往忘亡汪旺枉罔惘','wei':'为位未委味围微卫威唯伟维谓慰危尾魏违胃畏萎炜玮帷',
    'wen':'文问闻温稳纹吻蚊雯紊','weng':'翁嗡','wo':'我握窝卧沃涡蜗斡','wu':'五无物务武午舞吴误屋伍悟污乌呜巫侮梧毋捂',
    'xi':'西系细喜席习息希析洗稀袭吸惜戏悉熙膝锡溪熄媳','xia':'下夏暇峡狭厦瞎侠虾辖霞匣狎',
    'xian':'现先显线险县鲜限宪献闲仙陷贤纤咸羡衔弦娴','xiang':'想向相象像项香乡响享箱详湘巷厢翔祥镶飨',
    'xiao':'小笑消效晓校萧销潇宵啸逍箫','xie':'些写血谢协鞋械携斜泄卸蟹泻谐邪','xin':'新心信辛欣薪馨芯鑫',
    'xing':'行性星兴形型醒幸姓邢腥杏','xiong':'兄胸凶熊雄匈汹','xiu':'修秀休袖绣朽羞锈嗅',
    'xu':'需许须续徐绪虚叙蓄畜婿吁旭栩','xuan':'选宣旋悬玄喧轩绚眩璇','xue':'学血雪穴薛靴谑','xun':'寻训讯迅巡询熏勋循汛荀巽',
    'ya':'压牙亚雅呀鸭涯崖芽衙哑','yan':'眼言严演研烟验颜延沿燕盐岩掩厌炎艳宴雁焰阎唁',
    'yang':'样阳养洋扬仰央杨氧痒漾殃鸯','yao':'要药腰咬摇邀遥姚耀窑谣尧瑶舀','ye':'也业夜野叶爷页液耶椰掖腋',
    'yi':'一以已意义亿易衣艺依宜异议益移忆译疑椅姨翼伊','yin':'因银音引印饮阴隐姻吟殷淫胤',
    'ying':'应英影营迎映硬盈赢颖鹰婴蝇樱荧','yo':'哟','yong':'用永拥勇涌泳咏雍佣甬臃','you':'有又由右油游优友犹尤悠幽邮忧',
    'yu':'与于语雨玉鱼余预育遇域愈欲予育裕郁寓御喻誉虞渝','yuan':'原远元院愿圆源园员怨缘冤袁援渊苑',
    'yue':'月乐越约阅跃岳悦曰粤','yun':'运云允韵孕蕴匀芸陨','za':'杂砸咋匝咂','zai':'在再灾载栽仔宰哉崽',
    'zan':'咱赞攒暂簪','zang':'藏脏葬赃奘','zao':'早造遭糟枣灶燥噪藻凿','ze':'则责择泽咋仄','zei':'贼','zen':'怎',
    'zeng':'增赠憎曾综','zha':'炸扎诈闸渣乍札栅铡咤','zhai':'摘宅窄斋债寨','zhan':'站战占展粘瞻斩盏沾绽栈湛',
    'zhang':'长张章掌涨仗帐障彰樟杖璋','zhao':'找照着招赵召兆昭肇沼诏','zhe':'这者折哲浙遮辙蛰蔗褶',
    'zhen':'真阵镇针振震珍诊斟贞甄臻箴','zheng':'正整政证争征挣症蒸郑怔铮筝',
    'zhi':'之只知至制直治指志支值致纸质职植止织智置址执殖秩','zhong':'中重种众终钟忠衷肿踵',
    'zhou':'周州洲轴舟皱骤肘帚咒宙','zhu':'主住注助著逐朱竹猪煮诸珠筑柱祝株蛛驻瞩','zhua':'抓','zhuai':'拽',
    'zhuan':'转专赚砖撰篆','zhuang':'装庄壮状撞桩妆幢','zhui':'追坠缀椎赘','zhun':'准','zhuo':'桌捉啄着灼拙卓琢酌',
    'zi':'子自字资紫滋姿籽渍恣','zong':'总宗纵综踪粽','zou':'走奏邹','zu':'组族足祖租阻卒','zuan':'钻纂',
    'zui':'最嘴罪醉','zun':'尊遵','zuo':'作做左坐座昨佐撮柞'};
    const map = {};
    for (const [py, chars] of Object.entries(data)) {
        for (const ch of chars) { if (!map[ch]) map[ch] = py[0]; }
    }
    return map;
})();

function getPinyinAbbr(str) {
    if (!str) return '';
    let result = '';
    for (let i = 0; i < str.length; i++) {
        const ch = str[i];
        if (ch >= 'a' && ch <= 'z') result += ch;
        else if (ch >= 'A' && ch <= 'Z') result += ch.toLowerCase();
        else result += PINYIN_MAP[ch] || '';
    }
    return result;
}

const PREVIEW_CHARS_SMALL = '天地玄黄 宇宙洪荒 日月盈昃 辰宿列张';
const PREVIEW_CHARS_LARGE = 'Aa 洛书 123';

const CARD_GRADIENTS = [
    'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
    'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
    'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)',
    'linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%)',
    'linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%)',
    'linear-gradient(135deg, #d4fc79 0%, #96e6a1 100%)',
    'linear-gradient(135deg, #fbc2eb 0%, #a6c1ee 100%)',
    'linear-gradient(135deg, #fdcbf1 0%, #e6dee9 100%)',
    'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)',
];

function getFontGradient(fontId) {
    let hash = 0;
    for (let i = 0; i < fontId.length; i++) {
        hash = fontId.charCodeAt(i) + ((hash << 5) - hash);
    }
    return CARD_GRADIENTS[Math.abs(hash) % CARD_GRADIENTS.length];
}

// 已注入的字体 face 缓存，避免重复创建
const injectedFaces = new Set();

const App = {
    fonts: [],
    currentFont: '',
    pendingFont: null,
    deleteTarget: null,
    isLoading: false,
    isSwitching: false,
    searchQuery: '',
    showSearch: false,
    sortMode: 'name',
    theme: null,            // 'light' | 'dark' | null (auto)
    favorites: new Set(),   // 收藏字体 ID 集合
    dataSignature: '',
    dockActive: '',
    searchTimer: null,

    async init() {
        this.loadTheme();
        this.loadFavorites();
        this.bindEvents();
        this.bindScrollHeader();
        const restored = this.restoreDataCache();
        if (!restored) this.showSkeleton();
        await this.loadData({ background: restored });
        // 字体列表完成后再低优先级读取状态，避免多个 Root 命令争用启动时间。
        setTimeout(() => this.loadModuleInfo(), 0);
    },

    async loadModuleInfo() {
        let version = 'v12.8';
        try {
            const prop = await this.execShell(`sed -n 's/^version=//p' ${MODULE_DIR}/module.prop | head -n 1`);
            const raw = (prop || '').trim();
            const match = raw.match(/v?\d+(?:\.\d+)+/i);
            if (match) version = match[0].startsWith('v') ? match[0] : `v${match[0]}`;
        } catch (e) {
            console.warn('[洛书] 无法读取模块版本，使用内置版本', e);
        }
        document.querySelectorAll('[data-module-version]').forEach(el => { el.textContent = version; });
        const badge = document.getElementById('engineVersion');
        if (badge) badge.textContent = version;
        const state = document.getElementById('engineState');
        if (state) {
            try {
                const line = await this.execShell(`tail -n 120 ${MODULE_DIR}/logs/fontswitch.log 2>/dev/null | grep 'GMS-BRIDGE' | tail -n 1`);
                if (/成功=[1-9][0-9]*/.test(line)) state.innerHTML = '<i></i>GMS 已桥接';
                else if (/未发现/.test(line)) state.innerHTML = '<i></i>等待 GMS';
                else if (/失败=[1-9][0-9]*/.test(line)) state.innerHTML = '<i></i>部分适配';
            } catch (_) { /* 尚未生成开机日志时维持“运行中” */ }
        }
    },

    // ── 主题切换 ──
    loadTheme() {
        this.theme = localStorage.getItem('luoshu_theme') || null;
        this.applyTheme();
    },
    applyTheme() {
        if (this.theme) {
            document.documentElement.setAttribute('data-theme', this.theme);
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
        const label = document.getElementById('themeModeLabel');
        if (label) label.textContent = this.theme === 'dark' ? '深色' : this.theme === 'light' ? '浅色' : '跟随系统';
    },
    toggleTheme() {
        if (!this.theme) {
            // 当前是自动模式，根据系统偏好决定下一步
            const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            this.theme = isDark ? 'light' : 'dark';
        } else if (this.theme === 'dark') {
            this.theme = 'light';
        } else {
            this.theme = null; // 回到自动
        }
        localStorage.setItem('luoshu_theme', this.theme || '');
        this.applyTheme();
        const labels = { dark: '深色模式', light: '浅色模式' };
        this.showToast(this.theme ? labels[this.theme] : '自动模式（跟随系统）');
    },

    // ── 收藏管理 ──
    loadFavorites() {
        try {
            const data = JSON.parse(localStorage.getItem('luoshu_favorites') || '[]');
            this.favorites = new Set(data);
        } catch (e) { this.favorites = new Set(); }
    },
    saveFavorites() {
        localStorage.setItem('luoshu_favorites', JSON.stringify([...this.favorites]));
    },
    toggleFavorite(fontId) {
        if (this.favorites.has(fontId)) {
            this.favorites.delete(fontId);
        } else {
            this.favorites.add(fontId);
        }
        this.saveFavorites();
        this.renderList();
    },

    async execShell(cmd) {
        const { errno, stdout, stderr } = await exec(cmd);
        if (errno !== 0) {
            console.error('[洛书] exec error:', stderr);
            throw new Error(stderr || '命令执行失败');
        }
        return stdout;
    },

    // 骨架屏
    showSkeleton() {
        const container = document.getElementById('fontList');
        container.innerHTML = Array(4).fill(0).map(() => `
            <div class="font-card skeleton">
                <div class="card-left">
                    <div class="card-cover" style="background: var(--line);"></div>
                    <div class="card-body" style="flex:1">
                        <div style="height:16px;width:80px;background:var(--line);border-radius:4px;margin-bottom:8px"></div>
                        <div style="height:12px;width:160px;background:var(--line);border-radius:4px;margin-bottom:8px"></div>
                        <div style="height:12px;width:120px;background:var(--line);border-radius:4px"></div>
                    </div>
                </div>
            </div>
        `).join('');
    },

    restoreDataCache() {
        try {
            const cached = JSON.parse(localStorage.getItem(DATA_CACHE_KEY) || 'null');
            if (!cached || !cached.data || !Array.isArray(cached.data.fonts)) return false;
            this.applyFontData(cached.data, false);
            return true;
        } catch (_) {
            localStorage.removeItem(DATA_CACHE_KEY);
            return false;
        }
    },

    applyFontData(data, persist = true) {
        const signature = JSON.stringify(data);
        const changed = signature !== this.dataSignature;
        this.currentFont = data.current || '';
        this.fonts = data.fonts || [];
        this.stats = data.stats || { count: 0, totalSize: '0' };
        this.dataSignature = signature;
        if (persist) {
            try { localStorage.setItem(DATA_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), data })); } catch (_) { /* 缓存空间不足不影响使用 */ }
        }
        if (changed) {
            this.renderCurrent();
            this.renderStats();
            this.renderList();
        }
    },

    async loadData({ background = false, force = false } = {}) {
        if (this.isLoading) return;
        this.isLoading = true;
        try {
            const output = await this.execShell(`${FONT_MANAGER} action list${force ? ' refresh' : ''}`);
            const jsonLine = output.split('\n').find(l => l.trim().startsWith('{'));
            if (!jsonLine) { this.showError('无法获取字体列表'); return; }
            const res = JSON.parse(jsonLine.trim());
            if (res.status === 'ok' && res.data) {
                this.applyFontData(res.data);
            } else {
                if (!background) this.showError(res.message || '加载失败');
            }
        } catch (e) {
            console.error('[洛书] load error:', e);
            if (!background) this.showError('加载失败: ' + ((e && e.message) || String(e)));
        } finally {
            this.isLoading = false;
        }
    },

    // 只在需要预览时注入单个字体，避免进入页面就加载整个字体库。
    injectFontFace(font) {
        if (!font?.file || !font?.id) return;
        const safeId = this.safeId(font.id);
        if (injectedFaces.has(safeId)) return;
        injectedFaces.add(safeId);
        const el = document.getElementById('dynamicFontStyles') || document.createElement('style');
        el.id = 'dynamicFontStyles';
        el.textContent = (el.textContent || '') + `@font-face{font-family:"preview_${safeId}";src:url("${font.file}");font-display:swap;}`;
        if (!el.parentNode) document.head.appendChild(el);
    },

    scheduleFontFace(font) {
        if (!font || injectedFaces.has(this.safeId(font.id))) return;
        const run = () => this.injectFontFace(font);
        if ('requestIdleCallback' in window) requestIdleCallback(run, { timeout: 900 });
        else setTimeout(run, 180);
    },

    safeId(id) {
        return this.escape(id).replace(/[^a-zA-Z0-9]/g, '_');
    },

    renderStats() {
        const el = document.getElementById('statsPanel');
        if (!el) return;
        const count = this.stats?.count || 0;
        const totalSize = this.stats?.totalSize || '0';
        el.innerHTML = `
            <div class="stat-item"><div class="stat-value">${count}</div><div class="stat-label">字体</div></div>
            <div class="stat-divider"></div>
            <div class="stat-item"><div class="stat-value">${totalSize}</div><div class="stat-label">总大小</div></div>
        `;
        el.style.display = count > 0 ? 'flex' : 'none';
    },

    renderCurrent() {
        const nameEl = document.getElementById('currentFontName');
        const descEl = document.getElementById('currentFontDesc');
        const mainEl = document.getElementById('previewMain');
        const fullEl = document.getElementById('previewFull');
        const formatEl = document.getElementById('currentFormat');
        const sizeEl = document.getElementById('currentFontSize');
        const weightsEl = document.getElementById('currentWeights');

        if (!this.currentFont || this.currentFont === 'default') {
            nameEl.textContent = '系统默认字体';
            descEl.textContent = '使用系统自带字体';
            mainEl.textContent = '系统';
            fullEl.textContent = PREVIEW_CHARS_SMALL;
            formatEl.textContent = '系统字体';
            sizeEl.textContent = '系统';
            weightsEl.innerHTML = '<span class="weight-tag regular">常规</span><span class="weight-tag bold">粗体</span>';
            mainEl.style.fontFamily = '';
            fullEl.style.fontFamily = '';
            return;
        }

        const font = this.fonts.find(f => f.id === this.currentFont);
        nameEl.textContent = font ? font.name : this.currentFont;
        descEl.textContent = font && font.weights
            ? `字重: ${font.weights.map(w => WEIGHT_LABELS[w] || w).join(' / ')}`
            : '自定义字体';
        mainEl.textContent = font ? font.name.substring(0, 4) : '洛书';
        fullEl.textContent = PREVIEW_CHARS_SMALL;
        formatEl.textContent = font ? (font.format || 'TTF') : 'TTF';
        sizeEl.textContent = font ? (font.size || '') : '';

        if (font && font.weights) {
            weightsEl.innerHTML = font.weights.map(w =>
                `<span class="weight-tag ${w}">${WEIGHT_LABELS[w] || w}</span>`
            ).join('');
        }

        if (font && font.id) {
            const safe = this.safeId(font.id);
            mainEl.style.fontFamily = `'preview_${safe}', sans-serif`;
            fullEl.style.fontFamily = `'preview_${safe}', sans-serif`;
            this.scheduleFontFace(font);
        }
    },

    getSortedFonts() {
        let list = [...this.fonts].filter(f => f.id !== 'default');
        if (this.searchQuery) {
            const q = this.searchQuery.toLowerCase();
            const qPinyin = getPinyinAbbr(q);
            list = list.filter(f => {
                const name = (f.name || f.id).toLowerCase();
                const namePinyin = getPinyinAbbr(f.name || f.id);
                return name.includes(q) || namePinyin.includes(q) || namePinyin.includes(qPinyin);
            });
        }
        switch (this.sortMode) {
            case 'size': list.sort((a, b) => (parseInt(b.bytes) || 0) - (parseInt(a.bytes) || 0)); break;
            case 'date': list.sort((a, b) => (b.date || '').localeCompare(a.date || '')); break;
            default:
                // 先按收藏排序（收藏在前），再按名称排序
                list.sort((a, b) => {
                    const aFav = this.favorites.has(a.id) ? 0 : 1;
                    const bFav = this.favorites.has(b.id) ? 0 : 1;
                    if (aFav !== bFav) return aFav - bFav;
                    return (a.name || a.id).localeCompare(b.name || b.id);
                });
                break;
        }
        // 关键：当前正在使用的字体始终置顶（优先级高于排序模式和收藏）
        if (this.currentFont && this.currentFont !== 'default') {
            list.sort((a, b) => {
                const aCur = a.id === this.currentFont ? 0 : 1;
                const bCur = b.id === this.currentFont ? 0 : 1;
                return aCur - bCur;
            });
        }
        return list;
    },

    // ── 搜索高亮辅助 ──
    highlightText(text, query) {
        if (!query || query.length < 1) return this.escape(text);
        const escaped = this.escape(text);
        const q = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${q})`, 'gi');
        // 同时匹配拼音首字母高亮
        const qPinyin = getPinyinAbbr(query);
        if (qPinyin && qPinyin.length > 0) {
            const pinyinRegex = new RegExp(`(${qPinyin.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
            return escaped.replace(regex, '<mark class="search-match">$1</mark>')
                .replace(pinyinRegex, '<mark class="search-match">$1</mark>');
        }
        return escaped.replace(regex, '<mark class="search-match">$1</mark>');
    },

    renderList() {
        const container = document.getElementById('fontList');
        const countEl = document.getElementById('fontCount');
        const userFonts = this.getSortedFonts();
        countEl.textContent = `${userFonts.length} 款`;

        if (userFonts.length === 0) {
            container.innerHTML = this.searchQuery
                ? '<div class="empty"><div class="empty-icon">🔍</div><div class="empty-title">未找到匹配字体</div><div class="empty-desc">请尝试其他关键词</div></div>'
                : `<div class="onboarding">
                    <div class="onboarding-title">欢迎使用洛书</div>
                    <div class="onboarding-subtitle">三步开始使用自定义字体</div>
                    <div class="onboarding-steps">
                        <div class="onboarding-step"><div class="step-num">1</div><div class="step-content"><div class="step-title">准备字体</div><div class="step-desc">将 .ttf 字体文件放入<br><code>/sdcard/Fonts/</code> 目录</div></div></div>
                        <div class="onboarding-arrow">↓</div>
                        <div class="onboarding-step"><div class="step-num">2</div><div class="step-content"><div class="step-title">刷入模块</div><div class="step-desc">在 Magisk/KernelSU 中刷入本模块<br>用音量键选择字体</div></div></div>
                        <div class="onboarding-arrow">↓</div>
                        <div class="onboarding-step"><div class="step-num">3</div><div class="step-content"><div class="step-title">随时切换</div><div class="step-desc">在 WebUI 中点击字体卡片<br>选择字体并切换</div></div></div>
                    </div>
                    <div style="margin-top:20px; display:flex; gap:10px; justify-content:center;">
                        <button class="action-btn primary" style="flex:0 auto; padding:10px 20px;" onclick="App.openFontsFolder()">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px;"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
                            <span class="action-btn-title">打开 Fonts 文件夹</span>
                        </button>
                    </div>
                </div>`;
            return;
        }

        // 整体列表用一个简单动画，不用逐卡片 delay
        container.innerHTML = userFonts.map(font => {
            const isActive = font.id === this.currentFont;
            const isFav = this.favorites.has(font.id);
            const safe = this.safeId(font.id);
            const previewFamily = font.file ? `'preview_${safe}', sans-serif` : '';
            const weightTags = (font.weights || []).map(w =>
                `<span class="weight-tag ${w} ${isActive ? 'active' : ''}">${WEIGHT_LABELS[w] || w}</span>`
            ).join('');
            const gradient = getFontGradient(font.id);
            const titleHtml = this.searchQuery
                ? this.highlightText(font.name || font.id, this.searchQuery)
                : this.escape(font.name || font.id);
            return `
                <div class="font-card ${isActive ? 'active' : ''} ${isFav ? 'pinned' : ''}" data-id="${this.escape(font.id)}">
                    <div class="card-left">
                        <div class="card-cover" style="background:${gradient}">
                            <span class="card-cover-text" style="font-family:${previewFamily}">Aa</span>
                        </div>
                        <div class="card-body">
                            <div class="card-title-row">
                                <div class="card-title">${titleHtml}</div>
                                ${isActive ? '<span class="card-status">✓ 使用中</span>' : ''}
                            </div>
                            <div class="card-weights">${weightTags}</div>
                            <div class="card-preview-row">
                                <span class="card-preview-large" style="font-family:${previewFamily}">${PREVIEW_CHARS_LARGE}</span>
                                <span class="card-preview-small" style="font-family:${previewFamily}">${PREVIEW_CHARS_SMALL}</span>
                            </div>
                            <div class="card-meta">
                                ${isActive ? '<span class="card-hint">点击查看详情</span>' : '<span class="card-hint">点击切换字体</span>'}
                                <span class="card-fileinfo">${font.size || ''}${font.size && font.date ? ' · ' : ''}${font.date || ''}</span>
                            </div>
                        </div>
                    </div>
                    <div class="card-actions">
                        <button class="pin-badge ${isFav ? 'pinned' : ''}" data-pin="${this.escape(font.id)}" title="${isFav ? '取消置顶' : '置顶字体'}">${isFav ? '★' : '☆'}</button>
                        <button class="card-delete ${isActive ? 'current' : ''}" data-id="${this.escape(font.id)}" title="${isActive ? '删除当前字体（将恢复系统默认）' : '删除字体'}">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                        </button>
                    </div>
                </div>`;
        }).join('');

        // 事件绑定（事件委托，减少 listener 数量）
        container.onclick = (e) => {
            const pinBtn = e.target.closest('.pin-badge');
            if (pinBtn) {
                e.stopPropagation();
                const fontId = pinBtn.dataset.pin;
                this.toggleFavorite(fontId);
                return;
            }
            const card = e.target.closest('.font-card');
            const delBtn = e.target.closest('.card-delete');
            if (delBtn) {
                e.stopPropagation();
                const id = delBtn.dataset.id;
                const isCurrent = delBtn.classList.contains('current');
                this.deleteTarget = id;
                document.getElementById('deleteTarget').textContent = this.escape(id);
                const hintEl = document.querySelector('#deleteModal .modal-hint.warn');
                if (hintEl) hintEl.innerHTML = isCurrent
                    ? '<span class="hint-dot warn"></span>删除后将自动恢复系统默认字体'
                    : '<span class="hint-dot warn"></span>此操作不可撤销，字体文件将被永久删除';
                document.getElementById('deleteModal').classList.add('show');
            } else if (card) {
                this.showDetail(card.dataset.id);
            }
        };
    },

    showDetail(fontId) {
        const font = this.fonts.find(f => f.id === fontId);
        if (!font) return;
        this.injectFontFace(font);
        const isActive = fontId === this.currentFont;
        const safe = this.safeId(font.id);
        const previewFamily = font.file ? `'preview_${safe}', sans-serif` : '';
        const weightTags = (font.weights || []).map(w =>
            `<span class="weight-tag ${w} large">${WEIGHT_LABELS[w] || w}</span>`
        ).join('');

        document.getElementById('detailContent').innerHTML = `
            <div class="detail-preview" id="detailPreview" style="font-family:${previewFamily}">
                <div class="detail-preview-name" id="detailName">${this.escape(font.name || font.id)}</div>
                <div class="detail-preview-sub" id="detailSub">${PREVIEW_CHARS_LARGE}</div>
                <div class="detail-preview-small" id="detailSmall">${PREVIEW_CHARS_SMALL}</div>
                <input type="text" class="detail-preview-input" id="detailPreviewInput" placeholder="输入文字预览字体效果..." autocomplete="off" value="${this.escape(font.name || font.id)} Hello 世界 123">
            </div>
            <div class="detail-info">
                <div class="detail-row"><span class="detail-label">格式</span><span class="detail-value">${font.format || 'TTF'}</span></div>
                <div class="detail-row"><span class="detail-label">大小</span><span class="detail-value">${font.size || '未知'}</span></div>
                <div class="detail-row"><span class="detail-label">日期</span><span class="detail-value">${font.date || '未知'}</span></div>
                <div class="detail-row"><span class="detail-label">字重</span><span class="detail-value">${weightTags}</span></div>
            </div>
        `;

        // 绑定自定义预览输入事件
        setTimeout(() => {
            const input = document.getElementById('detailPreviewInput');
            const nameEl = document.getElementById('detailName');
            const subEl = document.getElementById('detailSub');
            const smallEl = document.getElementById('detailSmall');
            if (input && nameEl && subEl && smallEl) {
                const handler = () => {
                    const val = input.value || ' ';
                    nameEl.textContent = val.length > 12 ? val.substring(0, 12) + '…' : val;
                    subEl.textContent = val.length > 20 ? val.substring(0, 20) + '…' : val;
                    smallEl.textContent = val;
                };
                input.addEventListener('input', handler);
            }
        }, 100);

        const switchBtn = document.getElementById('detailSwitchBtn');
        const deleteBtn = document.getElementById('detailDeleteBtn');
        if (isActive) {
            switchBtn.textContent = '当前使用中';
            switchBtn.disabled = true;
            switchBtn.style.opacity = '0.5';
            deleteBtn.style.display = 'none';
        } else {
            switchBtn.textContent = '切换到此字体';
            switchBtn.disabled = false;
            switchBtn.style.opacity = '1';
            deleteBtn.style.display = '';
            switchBtn.onclick = () => { document.getElementById('detailModal').classList.remove('show'); this.switchFont(fontId); };
            deleteBtn.onclick = () => { document.getElementById('detailModal').classList.remove('show'); this.deleteTarget = fontId; document.getElementById('deleteTarget').textContent = this.escape(fontId); document.getElementById('deleteModal').classList.add('show'); };
        }
        document.getElementById('detailModal').classList.add('show');
    },

    toggleSearch() {
        this.showSearch = !this.showSearch;
        const bar = document.getElementById('searchBar');
        if (this.showSearch) {
            this.setDockActive('search');
            bar.classList.remove('hidden');
            bar.scrollIntoView({ behavior: 'smooth', block: 'start' });
            setTimeout(() => document.getElementById('searchInput').focus(), 220);
        }
        else {
            bar.classList.add('hidden');
            this.searchQuery = '';
            document.getElementById('searchInput').value = '';
            this.renderList();
            this.updateDockFromScroll();
        }
    },

    setDockActive(name) {
        if (this.dockActive === name) return;
        this.dockActive = name;
        document.querySelectorAll('.nav-btn').forEach(btn => {
            const active = btn.dataset.nav === name;
            btn.classList.toggle('active', active);
            btn.setAttribute('aria-current', active ? 'page' : 'false');
        });
    },

    updateDockFromScroll() {
        if (document.getElementById('helpModal')?.classList.contains('show')) return this.setDockActive('more');
        if (this.showSearch) return this.setDockActive('search');
        const list = document.getElementById('listSection');
        const atLibrary = list && window.scrollY + window.innerHeight * .42 >= list.offsetTop;
        this.setDockActive(atLibrary ? 'library' : 'home');
    },

    scrollToSection(name) {
        if (this.showSearch) this.toggleSearch();
        if (name === 'home') window.scrollTo({ top: 0, behavior: 'smooth' });
        if (name === 'library') document.getElementById('listSection')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        this.setDockActive(name);
    },

    bindScrollHeader() {
        let ticking = false;
        let compact = null;
        const update = () => {
            const nextCompact = window.scrollY > 42;
            if (nextCompact !== compact) {
                compact = nextCompact;
                document.body.classList.toggle('compact-header', compact);
            }
            this.updateDockFromScroll();
            ticking = false;
        };
        window.addEventListener('scroll', () => {
            if (!ticking) { requestAnimationFrame(update); ticking = true; }
        }, { passive: true });
        update();
    },

    cycleSort() {
        const modes = ['name', 'size', 'date'];
        const labels = { name: '名称', size: '大小', date: '日期' };
        this.sortMode = modes[(modes.indexOf(this.sortMode) + 1) % modes.length];
        this.showToast(`已按${labels[this.sortMode]}排序`);
        this.renderList();
    },

    // ── 上传字体功能已移除（仅保留本地字体切换/系统替换） ──

    bindEvents() {
        // 主题切换
        document.getElementById('themeToggleBtn').addEventListener('click', () => this.toggleTheme());

        document.getElementById('homeNavBtn').addEventListener('click', () => this.scrollToSection('home'));
        document.getElementById('libraryNavBtn').addEventListener('click', () => this.scrollToSection('library'));
        document.getElementById('moreNavBtn').addEventListener('click', () => {
            if (this.showSearch) this.toggleSearch();
            document.getElementById('helpModal').classList.add('show');
            this.setDockActive('more');
        });

        document.getElementById('refreshBtn').addEventListener('click', () => {
            if (this.isLoading) return;
            const btn = document.getElementById('refreshBtn');
            btn.classList.add('spinning');
            setTimeout(() => btn.classList.remove('spinning'), 600);
            this.loadData({ background: true, force: true });
        });
        document.getElementById('searchToggleBtn').addEventListener('click', () => this.toggleSearch());
        document.getElementById('searchCloseBtn').addEventListener('click', () => this.toggleSearch());
        document.getElementById('searchInput').addEventListener('input', (e) => {
            clearTimeout(this.searchTimer);
            const value = e.target.value.trim();
            this.searchTimer = setTimeout(() => { this.searchQuery = value; this.renderList(); }, 100);
        });
        document.getElementById('sortBtn')?.addEventListener('click', () => this.cycleSort());

        // 弹窗事件委托
        const modalClose = (id) => document.getElementById(id).classList.remove('show');
        document.getElementById('confirmBtn').addEventListener('click', () => { modalClose('modal'); if (this.pendingFont) this.switchFont(this.pendingFont); });
        document.getElementById('cancelBtn').addEventListener('click', () => { modalClose('modal'); this.pendingFont = null; });
        document.getElementById('modal').addEventListener('click', (e) => { if (e.target.id === 'modal') modalClose('modal'); });
        document.getElementById('confirmDeleteBtn').addEventListener('click', () => { modalClose('deleteModal'); if (this.deleteTarget) this.deleteFont(this.deleteTarget); });
        document.getElementById('cancelDeleteBtn').addEventListener('click', () => { modalClose('deleteModal'); this.deleteTarget = null; });
        document.getElementById('deleteModal').addEventListener('click', (e) => { if (e.target.id === 'deleteModal') modalClose('deleteModal'); });
        document.getElementById('restartUIBtn').addEventListener('click', () => document.getElementById('restartModal').classList.add('show'));
        document.getElementById('confirmRestartBtn').addEventListener('click', () => { modalClose('restartModal'); this.restartUI(); });
        document.getElementById('cancelRestartBtn').addEventListener('click', () => modalClose('restartModal'));
        document.getElementById('restartModal').addEventListener('click', (e) => { if (e.target.id === 'restartModal') modalClose('restartModal'); });
        document.getElementById('resetDefaultBtn').addEventListener('click', () => { document.getElementById('targetFont').textContent = '系统默认'; this.pendingFont = 'default'; document.getElementById('modal').classList.add('show'); });
        document.getElementById('detailCancelBtn').addEventListener('click', () => modalClose('detailModal'));
        document.getElementById('detailModal').addEventListener('click', (e) => { if (e.target.id === 'detailModal') modalClose('detailModal'); });
        const closeHelp = () => { modalClose('helpModal'); this.updateDockFromScroll(); };
        document.getElementById('closeHelpBtn').addEventListener('click', closeHelp);
        document.getElementById('helpModal').addEventListener('click', (e) => { if (e.target.id === 'helpModal') closeHelp(); });
    },

    async switchFont(fontId) {
        // 防抖：切换进行中禁止重复点击，避免重复执行大量文件复制导致卡顿
        if (this.isSwitching) return;
        this.isSwitching = true;
        this.showToast(fontId === 'default' ? '正在恢复默认字体...' : '正在切换字体，请稍候...');
        document.body.classList.add('switching');
        try {
            const output = await this.execShell(`${FONT_MANAGER} action switch "${fontId}"`);
            const jsonLine = output.split('\n').find(l => l.trim().startsWith('{'));
            if (jsonLine) {
                const res = JSON.parse(jsonLine.trim());
                if (res.status === 'ok') {
                    this.showToast(fontId === 'default' ? '✓ 已恢复默认字体' : '✓ 切换成功！重启手机后生效');
                    // 更新页面与本地缓存（当前字体会自动置顶）。
                    this.applyFontData({ current: fontId, fonts: this.fonts, stats: this.stats });
                    // 平滑滚动到列表顶部，让置顶的当前字体可见
                    requestAnimationFrame(() => {
                        const el = document.getElementById('listSection');
                        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    });
                } else {
                    this.showToast(res.message || '切换失败');
                }
            }
        } catch (e) {
            const msg = (e && e.message) ? e.message : String(e);
            this.showToast('切换失败: ' + msg);
        } finally {
            this.isSwitching = false;
            document.body.classList.remove('switching');
        }
    },

    async deleteFont(fontId) {
        this.showToast('正在删除字体...');
        try {
            const output = await this.execShell(`${FONT_MANAGER} action delete "${fontId}"`);
            const jsonLine = output.split('\n').find(l => l.trim().startsWith('{'));
            if (jsonLine) {
                const res = JSON.parse(jsonLine.trim());
                if (res.status === 'ok') {
                    this.showToast(`✓ 已删除 ${fontId}`);
                    // 从本地数据中移除，立即刷新
                    const fonts = this.fonts.filter(f => f.id !== fontId);
                    const current = this.currentFont === fontId ? 'default' : this.currentFont;
                    const totalBytes = fonts.reduce((sum, f) => sum + (parseInt(f.bytes) || 0), 0);
                    const formatSize = bytes => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
                    this.applyFontData({ current, fonts, stats: { count: fonts.length, totalSize: formatSize(totalBytes) } });
                } else {
                    this.showToast(res.message || '删除失败');
                }
            }
        } catch (e) {
            this.showToast('删除失败: ' + ((e && e.message) || String(e)));
        }
        this.deleteTarget = null;
    },

    async restartUI() {
        this.showToast('正在重启系统界面...');
        try {
            await this.execShell('pkill -f com.android.systemui || pkill -f systemui');
            await this.execShell('cmd activity write-settings');
            this.showToast('系统界面已重启！');
        } catch (e) {
            this.showToast('重启失败: ' + ((e && e.message) || String(e)));
        }
    },

    showToast(msg) {
        const el = document.getElementById('toast');
        el.textContent = msg;
        el.classList.add('show');
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
    },

    showError(msg) {
        document.getElementById('fontList').innerHTML = `
            <div class="empty"><div class="empty-icon">⚠️</div><div class="empty-title">${this.escape(msg)}</div><div class="empty-desc">点击右上角刷新重试</div></div>`;
    },

    async openFontsFolder() {
        try {
            await this.execShell('[ -d /sdcard/Fonts ] || mkdir -p /sdcard/Fonts');
            this.showToast('已创建 /sdcard/Fonts/ 目录，请将字体文件放入');
        } catch (e) {
            this.showToast('无法创建目录');
        }
    },

    escape(str) {
        return typeof str === 'string' ? str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') : '';
    }
};

document.addEventListener('DOMContentLoaded', () => App.init());
