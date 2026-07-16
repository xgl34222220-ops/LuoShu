// 洛书 WebUI - 支持 Magisk / KernelSU / SukiSU
// v13.4 Beta2 Hotfix2 — variable/static family weight control + ZIP package import

import { exec } from './kernelsu.js';
import { analyzeFontUrl, formatAnalysisReport } from './font_analyzer.js';

const MODULE_DIR = '/data/adb/modules/LuoShu';
const FONT_MANAGER = `${MODULE_DIR}/common/font_manager.sh`;
const DATA_CACHE_KEY = 'luoshu_font_data_v2';
const ANALYSIS_CACHE_KEY = 'luoshu_font_analysis_v2';
const USAGE_CACHE_KEY = 'luoshu_font_usage_v1';
const LAST_RESULT_KEY = 'luoshu_last_switch_result_v1';

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

const STATIC_WEIGHT_VALUES = { thin:300, light:350, regular:400, medium:500, semibold:600, bold:700, black:700 };
const STATIC_WEIGHT_CSS = { thin:100, light:300, regular:400, medium:500, semibold:600, bold:700, black:900, variable:400 };

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
    usageCounts: {},
    analysisCache: {},
    lastSwitchResult: null,
    dataSignature: '',
    dockActive: '',
    searchTimer: null,
    emojis: [],
    currentEmoji: 'default',
    textRebootRequired: false,
    emojiRebootRequired: false,
    weightRebootRequired: false,
    pendingRiskFont: null,
    pendingEmoji: null,
    isEmojiSwitching: false,
    importPackages: [],
    isImporting: false,
    fontWeightState: null,

    async init() {
        this.loadTheme();
        this.loadFavorites();
        this.loadUsageCounts();
        this.loadAnalysisCache();
        this.loadLastSwitchResult();
        this.bindEvents();
        this.bindScrollHeader();
        this.bindViewportCompatibility();
        this.bindModalCompatibility();
        const restored = this.restoreDataCache();
        if (!restored) this.showSkeleton();
        await this.loadData({ background: restored });
        await Promise.all([this.loadEmojis(), this.loadRebootStatus()]);
        // 字体列表完成后再低优先级读取状态，避免多个 Root 命令争用启动时间。
        setTimeout(() => this.loadModuleInfo(), 0);
        this.renderSwitchResult();
    },

    async loadModuleInfo() {
        let version = 'v13.4 Beta2 Hotfix2';
        try {
            const prop = await this.execShell(`sed -n 's/^version=//p' ${MODULE_DIR}/module.prop | head -n 1`);
            const raw = (prop || '').trim();
            if (raw) version = raw.startsWith('v') ? raw : `v${raw}`;
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

    loadUsageCounts() {
        try { this.usageCounts = JSON.parse(localStorage.getItem(USAGE_CACHE_KEY) || '{}') || {}; }
        catch (_) { this.usageCounts = {}; }
    },
    recordUsage(fontId) {
        if (!fontId || fontId === 'default') return;
        this.usageCounts[fontId] = (Number(this.usageCounts[fontId]) || 0) + 1;
        localStorage.setItem(USAGE_CACHE_KEY, JSON.stringify(this.usageCounts));
    },
    loadAnalysisCache() {
        try { this.analysisCache = JSON.parse(localStorage.getItem(ANALYSIS_CACHE_KEY) || '{}') || {}; }
        catch (_) { this.analysisCache = {}; }
    },
    saveAnalysisCache() {
        try { localStorage.setItem(ANALYSIS_CACHE_KEY, JSON.stringify(this.analysisCache)); }
        catch (_) { /* WebView 存储不足时忽略 */ }
    },
    loadLastSwitchResult() {
        try { this.lastSwitchResult = JSON.parse(localStorage.getItem(LAST_RESULT_KEY) || 'null'); }
        catch (_) { this.lastSwitchResult = null; }
    },
    saveLastSwitchResult(result) {
        this.lastSwitchResult = result;
        localStorage.setItem(LAST_RESULT_KEY, JSON.stringify(result));
        this.renderSwitchResult();
    },
    renderSwitchResult() {
        const el = document.getElementById('switchResult');
        if (!el) return;
        const result = this.lastSwitchResult;
        if (!result) { el.hidden = true; return; }
        const ok = result.status === 'success';
        const time = result.time ? new Date(result.time).toLocaleString([], { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }) : '';
        el.className = `switch-result ${ok ? 'success' : 'failed'}`;
        el.innerHTML = `<span class="switch-result-icon">${ok ? '✓' : '!'}</span><span class="switch-result-copy"><strong>${ok ? '字体应用完成' : '字体应用失败'}</strong><small>${this.escape(result.font || '未知字体')}${time ? ` · ${time}` : ''}${result.message ? ` · ${this.escape(result.message)}` : ''}</small></span>`;
        el.hidden = false;
    },
    analysisKey(font) {
        return `${font.id}|${font.bytes || 0}|${font.date || ''}|${font.file || ''}`;
    },
    async analyzeFont(font, force = false) {
        if (!font?.file) throw new Error('字体预览文件不可用');
        const key = this.analysisKey(font);
        if (!force && this.analysisCache[key]) return this.analysisCache[key];
        const result = await analyzeFontUrl(font.file);
        this.analysisCache[key] = result;
        this.saveAnalysisCache();
        return result;
    },
    coverageRow(label, item, tone = '') {
        return `<div class="coverage-row"><span>${label}</span><div class="coverage-track"><i class="${tone}" style="width:${Math.max(2, item.percent)}%"></i></div><b>${item.percent}%</b></div>`;
    },
    renderAnalysis(container, font, result) {
        if (!container) return;
        const c = result.coverage;
        const assessment = result.assessment;
        const warningHtml = assessment.warnings.length
            ? `<div class="analysis-warnings">${assessment.warnings.map(w => `<span>⚠ ${this.escape(w)}</span>`).join('')}</div>`
            : '<div class="analysis-ok">✓ 未发现明显的字体文件风险</div>';
        const axes = result.variable?.axes || [];
        const weightAxis = axes.find(a => String(a.tag || '').trim() === 'wght');
        const axesHtml = axes.length ? `<div class="variable-panel"><div class="variable-title">可变字体轴 · ${axes.length} 个</div>${axes.map(a => `<div class="variable-axis"><b>${this.escape(a.tag)}</b><span>${a.min} — ${a.max}</span><small>默认 ${a.default}</small></div>`).join('')}<div class="analysis-note">预览会直接使用字体的可变轴；系统应用使用 Android 全局字重调节，完整生效建议重启。</div></div>${weightAxis ? '<div class="variable-weight-control" id="variableWeightControl"><div class="analysis-loading"><span></span>正在读取系统字重设置…</div></div>' : ''}` : '';
        container.innerHTML = `
            <div class="analysis-head"><div><small>字符抽样检测</small><strong>${assessment.label}</strong></div><span class="analysis-score ${assessment.level}">${assessment.score}</span></div>
            <div class="coverage-list">
                ${this.coverageRow('常用中文', c.cjk, c.cjk.percent < 70 ? 'warn' : '')}
                ${this.coverageRow('英文字母', c.latin, c.latin.percent < 90 ? 'warn' : '')}
                ${this.coverageRow('数字', c.digits, c.digits.percent < 100 ? 'warn' : '')}
                ${this.coverageRow('标点符号', c.punctuation, c.punctuation.percent < 60 ? 'warn' : '')}
                ${this.coverageRow('特殊符号', c.symbols, c.symbols.percent < 35 ? 'warn' : '')}
                ${this.coverageRow('私用区', c.pua, c.pua.percent >= 22 ? 'danger' : 'muted')}
            </div>
            ${axesHtml}
            ${warningHtml}
            <div class="analysis-note">抽样结果只反映字体自身字符映射；缺失字符仍可能由 Android fallback 字体补齐。</div>
            <button class="analysis-report-btn" id="copyAnalysisReportBtn" type="button">复制检测报告</button>`;
        document.getElementById('copyAnalysisReportBtn')?.addEventListener('click', () => this.copyText(formatAnalysisReport(font, result), '检测报告已复制'));
        if (weightAxis) this.bindVariableWeightControl(font, weightAxis);
    },
    async loadFontWeightState(force = false) {
        if (!force && this.fontWeightState) return this.fontWeightState;
        const output = await this.execShell(`${FONT_MANAGER} action font_weight_status`);
        const line = output.split('\n').find(v => v.trim().startsWith('{'));
        const res = line ? JSON.parse(line.trim()) : null;
        if (res?.status !== 'ok') throw new Error(res?.message || '无法读取系统字体粗细');
        this.fontWeightState = res.data || {};
        return this.fontWeightState;
    },
    applyVariablePreview(weight) {
        const value = Number(weight) || 400;
        ['detailPreview', 'detailName', 'detailSub', 'detailSmall', 'detailPreviewInput'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.style.fontVariationSettings = `"wght" ${value}`;
            el.style.fontWeight = String(value);
        });
    },
    async bindVariableWeightControl(font, axis) {
        const box = document.getElementById('variableWeightControl');
        if (!box) return;
        const axisMin = Math.ceil(Number(axis.min) || 100);
        const axisMax = Math.floor(Number(axis.max) || 900);
        const safeMin = Math.max(300, axisMin);
        const safeMax = Math.min(700, axisMax);
        if (safeMin > safeMax) {
            box.innerHTML = '<div class="variable-weight-unavailable"><strong>此字体的 wght 轴不在系统安全调节范围内</strong><small>仍可保留字体自身的可变字重层级。</small></div>';
            return;
        }
        try {
            const state = await this.loadFontWeightState();
            const initial = Math.min(safeMax, Math.max(safeMin, Number(state.weight) || Math.round(Number(axis.default) || 400)));
            const presets = [300, 400, 500, 600, 700].filter(v => v >= safeMin && v <= safeMax);
            box.innerHTML = `
                <div class="variable-weight-head"><div><small>系统字体粗细</small><strong id="variableWeightValue">${initial}</strong></div><span id="variableWeightDelta">${initial === 400 ? '标准' : initial > 400 ? `+${initial - 400}` : `${initial - 400}`}</span></div>
                <input class="variable-weight-slider" id="variableWeightSlider" type="range" min="${safeMin}" max="${safeMax}" step="10" value="${initial}" aria-label="字体粗细">
                <div class="variable-weight-scale"><span>${safeMin}</span><span>400</span><span>${safeMax}</span></div>
                <div class="variable-weight-presets">${presets.map(v => `<button type="button" data-variable-weight="${v}" class="${v === initial ? 'active' : ''}">${v}</button>`).join('')}</div>
                <div class="variable-weight-note">字体轴范围 ${axisMin}–${axisMax}，系统安全应用范围 ${safeMin}–${safeMax}。预览立即变化；应用后即时写入系统，未更新的 App 重新打开即可，通常无需完整重启。</div>
                <div class="variable-weight-actions"><button type="button" id="resetVariableWeightBtn">恢复系统原值</button><button type="button" class="primary" id="applyVariableWeightBtn">应用粗细</button></div>`;
            const slider = document.getElementById('variableWeightSlider');
            const valueEl = document.getElementById('variableWeightValue');
            const deltaEl = document.getElementById('variableWeightDelta');
            const sync = value => {
                const v = Number(value) || 400;
                slider.value = String(v);
                valueEl.textContent = String(v);
                deltaEl.textContent = v === 400 ? '标准' : v > 400 ? `+${v - 400}` : `${v - 400}`;
                box.querySelectorAll('[data-variable-weight]').forEach(btn => btn.classList.toggle('active', Number(btn.dataset.variableWeight) === v));
                this.applyVariablePreview(v);
            };
            slider.addEventListener('input', e => sync(e.target.value));
            box.querySelectorAll('[data-variable-weight]').forEach(btn => btn.addEventListener('click', () => sync(btn.dataset.variableWeight)));
            document.getElementById('applyVariableWeightBtn')?.addEventListener('click', async e => {
                const btn = e.currentTarget;
                const value = Number(slider.value) || 400;
                btn.disabled = true; btn.textContent = '正在应用…';
                try {
                    const output = await this.execShell(`${FONT_MANAGER} action font_weight_set ${value}`);
                    const line = output.split('\n').find(v => v.trim().startsWith('{'));
                    const res = line ? JSON.parse(line.trim()) : null;
                    if (res?.status !== 'ok') throw new Error(res?.message || '粗细应用失败');
                    this.fontWeightState = { ...(this.fontWeightState || {}), ...(res.data || {}), supported: true };
                    this.weightRebootRequired = false;
                    this.updateRebootUI();
                    this.showToast(res.data?.message || `字体粗细已设为 ${value}`);
                } catch (err) { this.showToast((err && err.message) || String(err)); }
                finally { btn.disabled = false; btn.textContent = '应用粗细'; }
            });
            document.getElementById('resetVariableWeightBtn')?.addEventListener('click', async e => {
                const btn = e.currentTarget;
                btn.disabled = true; btn.textContent = '正在恢复…';
                try {
                    const output = await this.execShell(`${FONT_MANAGER} action font_weight_reset`);
                    const line = output.split('\n').find(v => v.trim().startsWith('{'));
                    const res = line ? JSON.parse(line.trim()) : null;
                    if (res?.status !== 'ok') throw new Error(res?.message || '恢复失败');
                    this.fontWeightState = null;
                    this.weightRebootRequired = false;
                    this.updateRebootUI();
                    sync(Math.min(safeMax, Math.max(safeMin, Number(res.data?.weight) || 400)));
                    this.showToast(res.data?.message || '已恢复系统原始字体粗细');
                } catch (err) { this.showToast((err && err.message) || String(err)); }
                finally { btn.disabled = false; btn.textContent = '恢复系统原值'; }
            });
            sync(initial);
            if (state.supported === false) {
                box.querySelectorAll('button,input').forEach(el => { el.disabled = true; });
                box.insertAdjacentHTML('beforeend', '<div class="variable-weight-unavailable"><small>当前系统未提供字体粗细设置接口，仅支持实时预览。</small></div>');
            }
        } catch (e) {
            box.innerHTML = `<div class="variable-weight-unavailable"><strong>系统粗细读取失败</strong><small>${this.escape((e && e.message) || String(e))}</small></div>`;
        }
    },
    applyStaticFamilyPreview(weight) {
        const value = Number(weight) || 400;
        ['detailPreview','detailName','detailSub','detailSmall','detailPreviewInput'].forEach(id => {
            const el = document.getElementById(id); if (!el) return;
            el.style.fontVariationSettings = 'normal';
            el.style.fontWeight = String(value);
        });
    },
    async bindStaticFamilyControl(font) {
        const box = document.getElementById('staticFamilyControl');
        if (!box) return;
        const roles = (font.weights || []).filter(role => role !== 'variable' && STATIC_WEIGHT_VALUES[role]);
        if (roles.length < 2) { box.remove(); return; }
        try {
            const state = await this.loadFontWeightState();
            const current = Number(state.weight) || 400;
            const available = roles.map(role => ({role,value:STATIC_WEIGHT_VALUES[role],css:STATIC_WEIGHT_CSS[role]||400,label:WEIGHT_LABELS[role]||role}));
            let selected = available.reduce((best,item) => Math.abs(item.value-current) < Math.abs(best.value-current) ? item : best, available[0]);
            box.innerHTML = `
                <div class="static-family-head"><div><small>多字重静态家族</small><strong id="staticWeightName">${this.escape(selected.label)}</strong></div><span>${available.length} 档可选</span></div>
                <div class="static-weight-presets">${available.map(item => `<button type="button" data-static-role="${item.role}" class="${item.role===selected.role?'active':''}"><b>${this.escape(item.label)}</b><small>${item.value}</small></button>`).join('')}</div>
                <div class="static-family-note">这是多个独立固定字重文件，不是连续可变轴。系统仍会按正文、标题和粗体请求自动匹配各文件；这里调整整体粗细偏移。预览立即变化，应用后通常无需完整重启，未更新的 App 重新打开即可。</div>
                <div class="variable-weight-actions"><button type="button" id="resetStaticWeightBtn">恢复系统原值</button><button type="button" class="primary" id="applyStaticWeightBtn">应用所选粗细</button></div>`;
            const nameEl=document.getElementById('staticWeightName');
            const choose=btn=>{ selected=available.find(x=>x.role===btn.dataset.staticRole)||selected; box.querySelectorAll('[data-static-role]').forEach(x=>x.classList.toggle('active',x===btn)); if(nameEl) nameEl.textContent=selected.label; this.applyStaticFamilyPreview(selected.css); };
            box.querySelectorAll('[data-static-role]').forEach(btn=>btn.addEventListener('click',()=>choose(btn)));
            document.getElementById('applyStaticWeightBtn')?.addEventListener('click',async e=>{
                const btn=e.currentTarget; btn.disabled=true; btn.textContent='正在应用…';
                try { const output=await this.execShell(`${FONT_MANAGER} action font_weight_set ${selected.value}`); const line=output.split('\n').find(v=>v.trim().startsWith('{')); const res=line?JSON.parse(line.trim()):null; if(res?.status!=='ok') throw new Error(res?.message||'粗细应用失败'); this.fontWeightState={...(this.fontWeightState||{}),...(res.data||{}),supported:true}; this.weightRebootRequired=false; this.updateRebootUI(); this.showToast(`已切换为${selected.label}偏移；未更新的应用请重新打开`); }
                catch(err){ this.showToast((err&&err.message)||String(err)); }
                finally{ btn.disabled=false; btn.textContent='应用所选粗细'; }
            });
            document.getElementById('resetStaticWeightBtn')?.addEventListener('click',async e=>{
                const btn=e.currentTarget; btn.disabled=true; btn.textContent='正在恢复…';
                try { const output=await this.execShell(`${FONT_MANAGER} action font_weight_reset`); const line=output.split('\n').find(v=>v.trim().startsWith('{')); const res=line?JSON.parse(line.trim()):null; if(res?.status!=='ok') throw new Error(res?.message||'恢复失败'); this.fontWeightState=null; this.weightRebootRequired=false; this.updateRebootUI(); const v=Number(res.data?.weight)||400; const target=available.reduce((best,item)=>Math.abs(item.value-v)<Math.abs(best.value-v)?item:best,available[0]); const targetBtn=box.querySelector(`[data-static-role="${target.role}"]`); if(targetBtn) choose(targetBtn); this.showToast('已恢复系统原始字体粗细'); }
                catch(err){ this.showToast((err&&err.message)||String(err)); }
                finally{ btn.disabled=false; btn.textContent='恢复系统原值'; }
            });
            const initialBtn=box.querySelector(`[data-static-role="${selected.role}"]`); if(initialBtn) choose(initialBtn);
            if(state.supported===false){ box.querySelectorAll('button').forEach(el=>el.disabled=true); box.insertAdjacentHTML('beforeend','<div class="variable-weight-unavailable"><small>当前 ROM 未提供系统字重接口，仅支持详情页预览。</small></div>'); }
        } catch(e) { box.innerHTML=`<div class="variable-weight-unavailable"><strong>字重状态读取失败</strong><small>${this.escape((e&&e.message)||String(e))}</small></div>`; }
    },
    async loadDetailAnalysis(font, force = false) {
        const container = document.getElementById('fontAnalysis');
        if (!container) return;
        container.innerHTML = '<div class="analysis-loading"><span></span>正在读取字体字符映射…</div>';
        try {
            const result = await this.analyzeFont(font, force);
            this.renderAnalysis(container, font, result);
        } catch (e) {
            container.innerHTML = `<div class="analysis-error"><strong>检测失败</strong><span>${this.escape((e && e.message) || String(e))}</span><button id="retryAnalysisBtn" type="button">重新检测</button></div>`;
            document.getElementById('retryAnalysisBtn')?.addEventListener('click', () => this.loadDetailAnalysis(font, true));
        }
    },

    async loadRebootStatus() {
        try {
            const output = await this.execShell(`${FONT_MANAGER} action reboot_required`);
            const line = output.split('\n').find(v => v.trim().startsWith('{'));
            const res = line ? JSON.parse(line.trim()) : null;
            if (res?.status === 'ok') {
                this.textRebootRequired = Boolean(res.data?.text);
                this.emojiRebootRequired = Boolean(res.data?.emoji);
                this.weightRebootRequired = Boolean(res.data?.weight);
                this.updateRebootUI();
            }
        } catch (e) {
            console.warn('[洛书] 无法读取重启状态', e);
        }
    },

    updateRebootUI() {
        const pending = this.textRebootRequired || this.emojiRebootRequired || this.weightRebootRequired;
        document.body.classList.toggle('reboot-required', pending);
        const btn = document.getElementById('rebootDeviceBtn');
        const hint = btn?.querySelector('.action-btn-hint');
        if (btn) btn.classList.toggle('pending', pending);
        if (hint) {
            const pendingItems = [];
            if (this.textRebootRequired) pendingItems.push('文字');
            if (this.emojiRebootRequired) pendingItems.push('Emoji');
            if (this.weightRebootRequired) pendingItems.push('粗细');
            hint.textContent = pending ? `${pendingItems.join(' + ')}等待重启` : '完成字体应用';
        }
        const badge = document.querySelector('.current-badge');
        if (badge) badge.innerHTML = `<span class="pulse-dot"></span>${pending ? '配置待重启' : '正在使用'}`;
    },

    async loadEmojis() {
        const container = document.getElementById('emojiList');
        try {
            const output = await this.execShell(`${FONT_MANAGER} action emoji_list`);
            const line = output.split('\n').find(v => v.trim().startsWith('{'));
            const res = line ? JSON.parse(line.trim()) : null;
            if (res?.status !== 'ok') throw new Error(res?.message || 'Emoji 列表读取失败');
            this.currentEmoji = res.data?.current || 'default';
            this.emojis = Array.isArray(res.data?.emojis) ? res.data.emojis : [];
            this.renderEmojis();
        } catch (e) {
            if (container) container.innerHTML = `<div class="emoji-empty">${this.escape((e && e.message) || String(e))}</div>`;
        }
    },

    renderEmojis() {
        const current = document.getElementById('emojiCurrent');
        const list = document.getElementById('emojiList');
        if (!current || !list) return;
        const active = this.currentEmoji === 'default'
            ? { name: '系统默认 Emoji', size: '保留 ROM 原始表情' }
            : (this.emojis.find(v => v.id === this.currentEmoji) || { name: this.currentEmoji, size: '自定义 Emoji' });
        current.innerHTML = `<span class="emoji-sample">😀</span><div><strong>${this.escape(active.name || active.id)}</strong><small>${this.escape(active.size || '/sdcard/LuoShu/emoji/')}</small></div><span class="emoji-active">使用中</span>`;
        const items = [{ id:'default', name:'系统默认 Emoji', size:'不替换 NotoColorEmoji' }, ...this.emojis];
        list.innerHTML = items.map(item => {
            const isActive = item.id === this.currentEmoji;
            const invalid = item.id !== 'default' && item.valid === false;
            const note = invalid ? (item.error || '文件无效') : (item.warning || (item.format ? `${item.format} · ${item.size || ''}` : (item.size || '')));
            return `<button class="emoji-card ${isActive ? 'active' : ''} ${invalid ? 'invalid' : ''}" data-emoji="${this.escape(item.id)}" type="button" ${isActive || invalid ? 'disabled' : ''}>
                <span class="emoji-card-icon">${item.id === 'default' ? '🙂' : '😀'}</span>
                <span class="emoji-card-copy"><strong>${this.escape(item.name || item.id)}</strong><small>${this.escape(note)}</small></span>
                <span class="emoji-card-action">${invalid ? '无效' : (isActive ? '当前' : '选择')}</span>
            </button>`;
        }).join('');
        list.querySelectorAll('[data-emoji]').forEach(btn => btn.addEventListener('click', () => this.switchEmoji(btn.dataset.emoji)));
    },

    async waitForEmojiTask(taskId, timeoutMs = 70000) {
        const started = Date.now();
        while (Date.now() - started < timeoutMs) {
            await new Promise(resolve => setTimeout(resolve, 650));
            const output = await this.execShell(`${FONT_MANAGER} action emoji_status ${this.shellQuote(taskId)}`);
            const line = output.split('\n').find(v => v.trim().startsWith('{'));
            if (!line) continue;
            const res = JSON.parse(line.trim());
            if (res.status !== 'ok' || !res.data) continue;
            if (res.data.state === 'success' || res.data.state === 'failed') return res.data;
        }
        throw new Error('Emoji 任务超时，请查看日志');
    },

    async switchEmoji(emojiId, force = false) {
        if (this.emojiRebootRequired) { this.showToast('本次开机已更改 Emoji，请先重启手机'); return; }
        const targetEmoji = this.emojis.find(v => v.id === emojiId);
        if (!force && emojiId !== 'default' && targetEmoji && targetEmoji.color === false) {
            this.pendingEmoji = emojiId;
            document.getElementById('riskMessage').innerHTML = `<strong>${this.escape(targetEmoji.name || emojiId)}</strong><br>• 未检测到常见彩色 Emoji 表，可能显示为单色或无法正常渲染`;
            document.getElementById('riskModal').classList.add('show');
            return;
        }
        if (this.isEmojiSwitching) { this.showToast('Emoji 正在处理'); return; }
        this.isEmojiSwitching = true;
        this.showToast('正在准备 Emoji…');
        try {
            const output = await this.execShell(`${FONT_MANAGER} action emoji_switch_async ${this.shellQuote(emojiId)}`);
            const line = output.split('\n').find(v => v.trim().startsWith('{'));
            const res = line ? JSON.parse(line.trim()) : null;
            if (res?.status !== 'ok') throw new Error(res?.message || '无法启动 Emoji 任务');
            const status = await this.waitForEmojiTask(res.data?.task);
            if (status.state !== 'success') throw new Error(status.message || 'Emoji 应用失败');
            this.currentEmoji = emojiId;
            this.emojiRebootRequired = true;
            this.renderEmojis();
            this.updateRebootUI();
            this.showApplyDone('Emoji', emojiId === 'default' ? '系统默认 Emoji' : emojiId);
        } catch (e) {
            this.showToast('Emoji 失败: ' + ((e && e.message) || String(e)));
        } finally {
            this.isEmojiSwitching = false;
        }
    },

    async requestFontSwitch(fontId) {
        if (this.textRebootRequired) { this.showToast('本次开机已更改文字字体，请先重启手机'); return; }
        this.pendingFont = fontId;
        if (fontId === 'default') {
            document.getElementById('targetFont').textContent = '系统默认字体';
            document.getElementById('modal').classList.add('show');
            return;
        }
        const font = this.fonts.find(v => v.id === fontId);
        if (!font) { this.showToast('字体不存在'); return; }
        let validation;
        try {
            const validationOutput = await this.execShell(`${FONT_MANAGER} action validate ${this.shellQuote(fontId)}`);
            const validationLine = validationOutput.split('\n').find(v => v.trim().startsWith('{'));
            validation = validationLine ? JSON.parse(validationLine.trim()) : null;
            if (validation?.status !== 'ok' || validation.data?.valid === false) {
                throw new Error(validation?.message || validation?.data?.error || '字体文件未通过格式检测');
            }
        } catch (e) {
            this.showToast('无法应用: ' + ((e && e.message) || String(e)));
            return;
        }
        const risks = [];
        if (validation.data?.warning) risks.push(validation.data.warning);
        try {
            const result = await this.analyzeFont(font);
            risks.push(...(result.assessment?.warnings || []));
            if ((result.coverage?.cjk?.percent || 0) < 55) risks.unshift('常用中文覆盖较低，可能出现漏字');
            if ((result.coverage?.pua?.percent || 0) >= 22) risks.push('私用区字形较多，部分 ROM 图标可能异常');
        } catch (_) {
            risks.push('无法读取详细字符覆盖，请确认字体在当前 ROM 上可用');
        }
        if (risks.length) {
            this.pendingRiskFont = fontId;
            document.getElementById('riskMessage').innerHTML = `<strong>${this.escape(font.name || font.id)}</strong><br>${risks.slice(0,4).map(v => `• ${this.escape(v)}`).join('<br>')}`;
            document.getElementById('riskModal').classList.add('show');
            return;
        }
        document.getElementById('targetFont').textContent = font.name || font.id;
        document.getElementById('modal').classList.add('show');
    },

    showApplyDone(kind, name) {
        const message = document.getElementById('applyDoneMessage');
        if (message) message.textContent = `${kind}「${name}」已准备，将在完整重启后安全生效。`;
        document.getElementById('applyDoneModal')?.classList.add('show');
    },

    async rebootDevice() {
        try {
            this.showToast('正在重启手机…');
            await this.execShell(`${FONT_MANAGER} action reboot_device`);
        } catch (e) {
            this.showToast('重启失败: ' + ((e && e.message) || String(e)));
        }
    },

    async openPublicFolder(kind = 'fonts') {
        const safeKind = kind === 'emoji' ? 'emoji' : (kind === 'import' ? 'import' : 'fonts');
        const path = `/sdcard/LuoShu/${safeKind}`;
        const title = safeKind === 'emoji' ? 'Emoji' : (safeKind === 'import' ? '字体包导入' : '文字字体');
        try { await this.execShell(`mkdir -p "${path}" && chmod 0777 "${path}" 2>/dev/null || true`); }
        catch (_) { this.showToast('无法创建目录'); return; }
        const docId = encodeURIComponent(`primary:LuoShu/${safeKind}`);
        const intents = [
            `am start --user 0 -a android.intent.action.OPEN_DOCUMENT_TREE --eu android.provider.extra.INITIAL_URI 'content://com.android.externalstorage.documents/document/${docId}' --activity-new-task`,
            `am start --user 0 -a android.intent.action.VIEW -d 'content://com.android.externalstorage.documents/document/${docId}' -t 'vnd.android.document/directory' --activity-new-task`,
            `am start --user 0 -a android.intent.action.VIEW -d 'file://${path}' -t 'resource/folder' --activity-new-task`
        ];
        for (const intent of intents) {
            try {
                const output = await this.execShell(`result=$(${intent} 2>&1); echo "$result"; echo "$result" | grep -Eqi 'Error|Exception|unable to resolve|not found' && exit 1 || exit 0`);
                if (!/Error|Exception|unable to resolve|not found/i.test(output || '')) { this.showToast(`已打开${title}文件夹`); return; }
            } catch (_) { /* try next */ }
        }
        await this.copyText(`${path}/`, `${title}路径已复制`);
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

    // 只在需要预览时注入字体。静态多字重家族会为每个实际文件建立独立 face。
    injectFontFace(font) {
        if (!font?.file || !font?.id) return;
        const safeId = this.safeId(font.id);
        if (injectedFaces.has(safeId)) return;
        injectedFaces.add(safeId);
        const cssUrl = value => String(value || '').replace(/(["\\])/g, '\\$1');
        const family = `preview_${safeId}`;
        const variants = font.variants && typeof font.variants === 'object' ? font.variants : {};
        const entries = Object.entries(variants).filter(([, file]) => file);
        let rules;
        if (font.variable) rules = `@font-face{font-family:"${family}";src:url("${cssUrl(font.file)}");font-weight:100 900;font-style:normal;font-display:swap;}`;
        else if (entries.length) rules = entries.map(([role,file]) => `@font-face{font-family:"${family}";src:url("${cssUrl(file)}");font-weight:${STATIC_WEIGHT_CSS[role] || 400};font-style:normal;font-display:swap;}`).join('');
        else rules = `@font-face{font-family:"${family}";src:url("${cssUrl(font.file)}");font-weight:400;font-style:normal;font-display:swap;}`;
        const el = document.getElementById('dynamicFontStyles') || document.createElement('style');
        el.id = 'dynamicFontStyles';
        el.textContent = (el.textContent || '') + rules;
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
        mainEl.textContent = font ? font.name : '洛书';
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
            case 'usage': list.sort((a, b) => (Number(this.usageCounts[b.id]) || 0) - (Number(this.usageCounts[a.id]) || 0)); break;
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
                        <div class="onboarding-step"><div class="step-num">1</div><div class="step-content"><div class="step-title">准备字体</div><div class="step-desc">将 .ttf 字体文件放入<br><code>/sdcard/LuoShu/fonts/</code> 目录</div></div></div>
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
            const isInvalid = font.valid === false;
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
                <div class="font-card ${isActive ? 'active' : ''} ${isFav ? 'pinned' : ''} ${isInvalid ? 'invalid' : ''}" data-id="${this.escape(font.id)}">
                    <div class="card-left">
                        <div class="card-cover" style="background:${gradient}">
                            <span class="card-cover-text" style="font-family:${previewFamily}">Aa</span>
                        </div>
                        <div class="card-body">
                            <div class="card-title-row">
                                <div class="card-title">${titleHtml}</div>
                                ${isInvalid ? '<span class="card-status invalid">无效文件</span>' : (isActive ? '<span class="card-status">✓ 使用中</span>' : '')}
                            </div>
                            <div class="card-weights">${weightTags}${!font.variable && (font.weights || []).filter(w => w !== 'variable').length > 1 ? '<span class="family-adjust-badge">可调</span>' : ''}</div>
                            <div class="card-preview-row">
                                <span class="card-preview-large" style="font-family:${previewFamily}">${PREVIEW_CHARS_LARGE}</span>
                                <span class="card-preview-small" style="font-family:${previewFamily}">${PREVIEW_CHARS_SMALL}</span>
                            </div>
                            <div class="card-meta">
                                ${isInvalid ? `<span class="card-hint danger">${this.escape(font.error || '文件格式无效')}</span>` : (isActive ? `<span class="card-hint">${!font.variable && (font.weights || []).filter(w => w !== 'variable').length > 1 ? '点击详情调节字重' : '点击查看详情'}</span>` : '<span class="card-hint">点击切换字体</span>')}
                                <span class="card-fileinfo">${this.usageCounts[font.id] ? `使用 ${this.usageCounts[font.id]} 次 · ` : ''}${font.size || ''}${font.size && font.date ? ' · ' : ''}${font.date || ''}</span>
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
                <div class="detail-row"><span class="detail-label">字重类型</span><span class="detail-value">${font.variable ? '可变字体（连续调节）' : ((font.weights || []).length > 1 ? `静态多字重（${font.weights.length} 档）` : '单一字重')}</span></div>
                <div class="detail-row"><span class="detail-label">可用字重</span><span class="detail-value">${weightTags}</span></div>
                <div class="detail-row"><span class="detail-label">文件检测</span><span class="detail-value ${font.valid === false ? 'danger-text' : ''}">${font.valid === false ? this.escape(font.error || '未通过') : '通过'}</span></div>
                <div class="detail-row"><span class="detail-label">使用次数</span><span class="detail-value">${Number(this.usageCounts[font.id]) || 0} 次</span></div>
            </div>
            ${!font.variable && (font.weights || []).filter(w => w !== 'variable').length > 1 ? '<div class="static-family-control" id="staticFamilyControl"><div class="analysis-loading"><span></span>正在读取多字重状态…</div></div>' : ''}
            <div class="font-analysis" id="fontAnalysis"><div class="analysis-loading"><span></span>正在读取字体字符映射…</div></div>
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
                    nameEl.textContent = val;
                    subEl.textContent = val;
                    smallEl.textContent = val;
                };
                input.addEventListener('input', handler);
            }
        }, 100);

        const switchBtn = document.getElementById('detailSwitchBtn');
        const deleteBtn = document.getElementById('detailDeleteBtn');
        if (font.valid === false) {
            switchBtn.textContent = '文件无效，不能应用';
            switchBtn.disabled = true;
            switchBtn.style.opacity = '0.5';
            deleteBtn.style.display = '';
            deleteBtn.onclick = () => { document.getElementById('detailModal').classList.remove('show'); this.deleteTarget = fontId; document.getElementById('deleteTarget').textContent = this.escape(fontId); document.getElementById('deleteModal').classList.add('show'); };
        } else if (isActive) {
            switchBtn.textContent = '当前使用中';
            switchBtn.disabled = true;
            switchBtn.style.opacity = '0.5';
            deleteBtn.style.display = 'none';
        } else {
            switchBtn.textContent = '切换到此字体';
            switchBtn.disabled = false;
            switchBtn.style.opacity = '1';
            deleteBtn.style.display = '';
            switchBtn.onclick = () => { document.getElementById('detailModal').classList.remove('show'); this.requestFontSwitch(fontId); };
            deleteBtn.onclick = () => { document.getElementById('detailModal').classList.remove('show'); this.deleteTarget = fontId; document.getElementById('deleteTarget').textContent = this.escape(fontId); document.getElementById('deleteModal').classList.add('show'); };
        }
        document.getElementById('detailModal').classList.add('show');
        const detailScroller = document.getElementById('detailContent');
        if (detailScroller) detailScroller.scrollTop = 0;
        if (!font.variable && (font.weights || []).filter(w => w !== 'variable').length > 1) this.bindStaticFamilyControl(font);
        this.loadDetailAnalysis(font);
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
        const modes = ['name', 'size', 'date', 'usage'];
        const labels = { name: '名称', size: '大小', date: '日期', usage: '使用次数' };
        this.sortMode = modes[(modes.indexOf(this.sortMode) + 1) % modes.length];
        this.showToast(`已按${labels[this.sortMode]}排序`);
        this.renderList();
    },

    // ── 上传字体功能已移除（仅保留本地字体切换/系统替换） ──

    openImportModal() {
        document.getElementById('helpModal')?.classList.remove('show');
        document.getElementById('importModal')?.classList.add('show');
        const result = document.getElementById('importResult');
        if (result) { result.hidden = true; result.innerHTML = ''; }
        this.loadImportPackages();
    },

    async loadImportPackages() {
        const list = document.getElementById('importList');
        if (list) list.innerHTML = '<div class="analysis-loading"><span></span>正在扫描 ZIP 字体包…</div>';
        try {
            const output = await this.execShell(`${FONT_MANAGER} action import_list`);
            const line = output.split('\n').find(v => v.trim().startsWith('{'));
            const res = line ? JSON.parse(line.trim()) : null;
            if (res?.status !== 'ok') throw new Error(res?.message || '扫描失败');
            this.importPackages = Array.isArray(res.data?.packages) ? res.data.packages : [];
            this.renderImportPackages();
        } catch (e) {
            if (list) list.innerHTML = `<div class="import-empty"><strong>扫描失败</strong><small>${this.escape((e && e.message) || String(e))}</small></div>`;
        }
    },

    renderImportPackages() {
        const list = document.getElementById('importList');
        if (!list) return;
        if (!this.importPackages.length) {
            list.innerHTML = `<div class="import-empty"><strong>没有找到 ZIP 字体包</strong><small>先把其他字体模块 ZIP 放入 /sdcard/LuoShu/import/，再点击刷新。</small><button class="btn-cancel" id="emptyOpenImportBtn" type="button">打开导入目录</button></div>`;
            document.getElementById('emptyOpenImportBtn')?.addEventListener('click', () => this.openPublicFolder('import'));
            return;
        }
        list.innerHTML = this.importPackages.map(item => `
            <div class="import-package">
                <span class="import-package-icon">ZIP</span>
                <span class="import-package-copy"><strong>${this.escape(item.name || item.id)}</strong><small>${this.escape(item.size || '')}${item.date ? ` · ${this.escape(item.date)}` : ''}</small></span>
                <button class="import-package-btn" type="button" data-import-zip="${this.escape(item.id)}">自动识别</button>
            </div>`).join('');
        list.querySelectorAll('[data-import-zip]').forEach(btn => {
            btn.addEventListener('click', () => this.importZipPackage(btn.dataset.importZip, btn));
        });
    },

    async importZipPackage(zipId, button) {
        if (this.isImporting) { this.showToast('正在导入字体包'); return; }
        this.isImporting = true;
        const oldText = button?.textContent || '自动识别';
        if (button) { button.disabled = true; button.textContent = '识别中…'; }
        const resultBox = document.getElementById('importResult');
        if (resultBox) {
            resultBox.hidden = false;
            resultBox.className = 'import-result running';
            resultBox.innerHTML = '<strong>正在识别字体包…</strong><small>正在筛选中文主字体、可变字体和完整字重家族</small>';
        }
        // 先让 WebView 完成一次绘制，避免 Shell 桥接阻塞时按钮过很久才显示“识别中”。
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        await new Promise(resolve => setTimeout(resolve, 40));
        try {
            const output = await this.execShell(`${FONT_MANAGER} action import_zip ${this.shellQuote(zipId)}`);
            const line = output.split('\n').find(v => v.trim().startsWith('{'));
            const res = line ? JSON.parse(line.trim()) : null;
            if (res?.status !== 'ok') throw new Error(res?.message || '导入失败');
            const data = res.data || {};
            const modeLabel = data.mode === 'variable' ? '可变字体' : (data.mode === 'deduplicated' ? '重复别名去重' : (data.mode === 'family' ? '完整字重家族' : '单字体'));
            if (resultBox) {
                resultBox.hidden = false;
                resultBox.className = 'import-result success';
                resultBox.innerHTML = `<strong>✓ ${this.escape(data.message || '导入完成')}</strong>
                    <small>${this.escape(data.reason || '')}${data.source ? ` · 原文件 ${this.escape(data.source)}` : ''}</small>
                    <small>识别方式：${this.escape(modeLabel)} · 文字 ${Number(data.importedText) || 0} 个${Number(data.importedEmoji) ? ` · Emoji ${Number(data.importedEmoji)} 个` : ''}</small>
                    <small>通过检测 ${Number(data.valid) || 0} 个 · 无效 ${Number(data.invalid) || 0} 个 · 已忽略 ${Number(data.ignored) || 0} 个</small>`;
            }
            this.showToast(data.message || '字体包导入完成');
            await Promise.all([this.loadData({ background: true, force: true }), this.loadEmojis()]);
        } catch (e) {
            const msg = (e && e.message) || String(e);
            if (resultBox) {
                resultBox.hidden = false;
                resultBox.className = 'import-result failed';
                resultBox.innerHTML = `<strong>导入失败</strong><small>${this.escape(msg)}</small>`;
            }
            this.showToast('导入失败: ' + msg);
        } finally {
            this.isImporting = false;
            if (button) { button.disabled = false; button.textContent = oldText; }
        }
    },

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
        document.getElementById('rebootDeviceBtn')?.addEventListener('click', () => document.getElementById('rebootDeviceModal')?.classList.add('show'));
        document.getElementById('openEmojiFolderBtn')?.addEventListener('click', () => this.openPublicFolder('emoji'));
        document.getElementById('moreOpenEmojiFolderBtn')?.addEventListener('click', () => this.openPublicFolder('emoji'));
        document.getElementById('importZipBtn')?.addEventListener('click', () => this.openImportModal());
        document.getElementById('moreImportZipBtn')?.addEventListener('click', () => this.openImportModal());
        document.getElementById('openImportFolderBtn')?.addEventListener('click', () => this.openPublicFolder('import'));
        document.getElementById('refreshImportBtn')?.addEventListener('click', () => this.loadImportPackages());

        // 弹窗事件委托
        const modalClose = (id) => document.getElementById(id)?.classList.remove('show');
        document.getElementById('confirmRiskBtn')?.addEventListener('click', () => { const id = this.pendingRiskFont; const emoji = this.pendingEmoji; this.pendingRiskFont = null; this.pendingEmoji = null; modalClose('riskModal'); if (id) this.switchFont(id); else if (emoji) this.switchEmoji(emoji, true); });
        document.getElementById('cancelRiskBtn')?.addEventListener('click', () => { this.pendingRiskFont = null; this.pendingEmoji = null; modalClose('riskModal'); });
        document.getElementById('riskModal')?.addEventListener('click', e => { if (e.target.id === 'riskModal') modalClose('riskModal'); });
        document.getElementById('rebootLaterBtn')?.addEventListener('click', () => modalClose('applyDoneModal'));
        document.getElementById('rebootNowBtn')?.addEventListener('click', () => { modalClose('applyDoneModal'); this.rebootDevice(); });
        document.getElementById('confirmRebootDeviceBtn')?.addEventListener('click', () => { modalClose('rebootDeviceModal'); this.rebootDevice(); });
        document.getElementById('cancelRebootDeviceBtn')?.addEventListener('click', () => modalClose('rebootDeviceModal'));
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
        document.getElementById('resetDefaultBtn').addEventListener('click', () => this.requestFontSwitch('default'));
        document.getElementById('detailCancelBtn').addEventListener('click', () => modalClose('detailModal'));
        document.getElementById('detailModal').addEventListener('click', (e) => { if (e.target.id === 'detailModal') modalClose('detailModal'); });
        const closeImport = () => modalClose('importModal');
        document.getElementById('closeImportBtn')?.addEventListener('click', closeImport);
        document.getElementById('importModal')?.addEventListener('click', e => { if (e.target.id === 'importModal') closeImport(); });
        const closeHelp = () => { modalClose('helpModal'); this.updateDockFromScroll(); };
        document.getElementById('closeHelpBtn').addEventListener('click', closeHelp);
        document.getElementById('closeHelpTopBtn')?.addEventListener('click', closeHelp);
        document.getElementById('moreOpenFolderBtn')?.addEventListener('click', () => this.openPublicFolder('fonts'));
        document.getElementById('generateReportBtn')?.addEventListener('click', () => this.generateReport());
        document.getElementById('copyFontPathBtn')?.addEventListener('click', () => this.copyFontsPath());
        document.getElementById('helpModal').addEventListener('click', (e) => { if (e.target.id === 'helpModal') closeHelp(); });
    },

    async waitForSwitchTask(taskId, timeoutMs = 70000) {
        const started = Date.now();
        while (Date.now() - started < timeoutMs) {
            await new Promise(resolve => setTimeout(resolve, 650));
            const output = await this.execShell(`${FONT_MANAGER} action switch_status ${this.shellQuote(taskId)}`);
            const jsonLine = output.split('\n').find(l => l.trim().startsWith('{'));
            if (!jsonLine) continue;
            const res = JSON.parse(jsonLine.trim());
            if (res.status !== 'ok' || !res.data) continue;
            if (res.data.state === 'success' || res.data.state === 'failed') return res.data;
        }
        throw new Error('切换任务超时，请查看日志');
    },

    async switchFont(fontId) {
        if (this.isSwitching) { this.showToast('字体切换正在进行中'); return; }
        this.isSwitching = true;
        this.showToast(fontId === 'default' ? '正在恢复默认字体…' : '正在应用字体…');
        document.body.classList.add('switching');
        try {
            const output = await this.execShell(`${FONT_MANAGER} action switch_async ${this.shellQuote(fontId)}`);
            const jsonLine = output.split('\n').find(l => l.trim().startsWith('{'));
            if (!jsonLine) throw new Error('未收到切换任务信息');
            const res = JSON.parse(jsonLine.trim());
            if (res.status !== 'ok') throw new Error(res.message || '无法启动切换任务');
            const taskId = res.data?.task;
            if (!taskId) throw new Error('切换任务 ID 缺失');
            const status = await this.waitForSwitchTask(taskId);
            if (status.state !== 'success') throw new Error(status.message || '字体应用失败');

            this.applyFontData({ current: fontId, fonts: this.fonts, stats: this.stats });
            this.recordUsage(fontId);
            const displayName = fontId === 'default' ? '系统默认字体' : (this.fonts.find(v => v.id === fontId)?.name || fontId);
            this.saveLastSwitchResult({ status: 'success', font: displayName, time: Date.now(), message: status.message || '' });
            this.textRebootRequired = true;
            this.updateRebootUI();
            this.showToast(fontId === 'default' ? '✓ 已准备恢复系统默认字体' : '✓ 字体已准备，重启后全局生效');
            this.showApplyDone('文字字体', displayName);
            this.renderList();
            requestAnimationFrame(() => document.getElementById('currentCard')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
        } catch (e) {
            const msg = (e && e.message) ? e.message : String(e);
            this.saveLastSwitchResult({ status: 'failed', font: fontId === 'default' ? '系统默认字体' : fontId, time: Date.now(), message: msg });
            this.showToast('切换失败: ' + msg);
        } finally {
            this.isSwitching = false;
            document.body.classList.remove('switching');
        }
    },

    async deleteFont(fontId) {
        this.showToast('正在删除字体...');
        try {
            const output = await this.execShell(`${FONT_MANAGER} action delete ${this.shellQuote(fontId)}`);
            const jsonLine = output.split('\n').find(l => l.trim().startsWith('{'));
            if (jsonLine) {
                const res = JSON.parse(jsonLine.trim());
                if (res.status === 'ok') {
                    this.showToast(`✓ 已删除 ${fontId}`);
                    // 从本地数据中移除，立即刷新
                    const deletingCurrent = this.currentFont === fontId;
                    const fonts = this.fonts.filter(f => f.id !== fontId);
                    const current = deletingCurrent ? 'default' : this.currentFont;
                    const totalBytes = fonts.reduce((sum, f) => sum + (parseInt(f.bytes) || 0), 0);
                    const formatSize = bytes => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
                    this.applyFontData({ current, fonts, stats: { count: fonts.length, totalSize: formatSize(totalBytes) } });
                    await this.loadRebootStatus();
                    if (deletingCurrent) this.showApplyDone('文字字体', '系统默认字体');
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
        this.showToast('正在安全重启系统界面…');
        try {
            const output = await this.execShell(`${FONT_MANAGER} action restart_ui`);
            const line = output.split('
').find(v => v.trim().startsWith('{'));
            const res = line ? JSON.parse(line.trim()) : null;
            if (res && res.status !== 'ok') throw new Error(res.message || '系统界面重启失败');
            this.showToast(res?.data?.message || '系统界面已重启');
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

    async openFontsFolder() { return this.openPublicFolder('fonts'); },

    async generateReport() {
        try {
            this.showToast('正在生成诊断报告…');
            const output = await this.execShell(`${FONT_MANAGER} action report`);
            const line = output.split('\n').find(v => v.trim().startsWith('{'));
            const res = line ? JSON.parse(line.trim()) : null;
            if (res?.status !== 'ok') throw new Error(res?.message || '生成失败');
            await this.copyText(res.data?.path || '/sdcard/LuoShu/reports/', '报告已生成，路径已复制');
        } catch (e) {
            this.showToast('报告失败: ' + ((e && e.message) || String(e)));
        }
    },

    async copyText(text, successMessage = '已复制') {
        let copied = false;
        try { await navigator.clipboard.writeText(text); copied = true; }
        catch (_) {
            const input = document.createElement('textarea');
            input.value = text;
            input.setAttribute('readonly', '');
            input.style.cssText = 'position:fixed;left:-9999px;opacity:0';
            document.body.appendChild(input);
            input.select();
            try { copied = document.execCommand('copy'); } catch (_) { copied = false; }
            input.remove();
        }
        this.showToast(copied ? successMessage : '复制失败');
        return copied;
    },

    async copyFontsPath(showFeedback = true) {
        const path = '/sdcard/LuoShu/fonts/';
        let copied = false;
        try {
            await navigator.clipboard.writeText(path);
            copied = true;
        } catch (_) {
            const input = document.createElement('textarea');
            input.value = path;
            input.setAttribute('readonly', '');
            input.style.cssText = 'position:fixed;left:-9999px;opacity:0';
            document.body.appendChild(input);
            input.select();
            try { copied = document.execCommand('copy'); } catch (_) { copied = false; }
            input.remove();
        }
        if (showFeedback) this.showToast(copied ? '已复制 /sdcard/LuoShu/fonts/' : '字体路径：/sdcard/LuoShu/fonts/');
        return copied;
    },

    shellQuote(value) {
        return "'" + String(value ?? '').replace(/'/g, "'\\''") + "'";
    },

    escape(str) {
        return typeof str === 'string' ? str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') : '';
    }
};

window.App = App;
document.addEventListener('DOMContentLoaded', () => App.init());
