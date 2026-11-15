"""Crop catalogue: DSK (stat.gov.az) regional tables + FAO ECOCROP requirement records.

yield table = 2.x "məhsuldarlığı" (sentner/ha), prod table = 2.x "istehsalı" (ton).
eco = ECOCROP SCIENTNAME used for the climate-suitability model.
"""

CROPS = [
    # id, az, en, group, yield_tbl, prod_tbl, ecocrop scientific name
    ("bugda", "Buğda", "Wheat", "Dənli", "2.187", "2.113", "Triticum aestivum L."),
    ("arpa", "Arpa", "Barley", "Dənli", "2.188", "2.114", "Hordeum vulgare L."),
    ("qargidali", "Qarğıdalı (dən)", "Maize", "Dənli", "2.191", "2.117", "Zea mays L. s. mays"),
    ("celtik", "Çəltik", "Rice", "Dənli", "2.194", "2.120", "Oryza sativa L. s. japonica"),
    ("noxud", "Noxud", "Chickpea", "Paxlalı", "2.196", "2.122", "Cicer arietinum L."),
    ("lobya", "Lobya", "Bean", "Paxlalı", "2.197", "2.123", "Phaseolus vulgaris L."),
    ("mercimek", "Mərcimək", "Lentil", "Paxlalı", "2.198", "2.124", "Lens culinaris Medikus"),
    ("pambiq", "Pambıq", "Cotton", "Texniki", "2.202", "2.128", "Gossypium hirsutum L."),
    ("tutun", "Tütün", "Tobacco", "Texniki", "2.203", "2.129", "Nicotiana tabacum L."),
    ("seker-cugunduru", "Şəkər çuğunduru", "Sugar beet", "Texniki", "2.204", "2.130", "Beta vulgaris L. v vulgaris"),
    ("gunebaxan", "Günəbaxan", "Sunflower", "Texniki", "2.205", "2.131", "Helianthus annuus L v macro"),
    ("kartof", "Kartof", "Potato", "Tərəvəz", "2.206", "2.132", "Solanum tuberosum L."),
    ("terevez", "Tərəvəz (cəmi)", "Vegetables (total)", "Tərəvəz", "2.207", "2.133", None),
    ("kelem", "Kələm", "Cabbage", "Tərəvəz", "2.208", "2.134", "Brassica oleracea L.v capi."),
    ("xiyar", "Xiyar", "Cucumber", "Tərəvəz", "2.210", "2.136", "Cucumis sativus L."),
    ("pomidor", "Pomidor", "Tomato", "Tərəvəz", "2.211", "2.137", "Lycopersicon esculentum M."),
    ("sogan", "Baş soğan", "Onion", "Tərəvəz", "2.214", "2.140", "Allium cepa L. v cepa"),
    ("sarimsaq", "Sarımsaq", "Garlic", "Tərəvəz", "2.215", "2.141", "Allium sativum L."),
    ("badimcan", "Badımcan", "Eggplant", "Tərəvəz", "2.219", "2.145", "Solanum melongena L."),
    ("bibar", "Şirin bibər", "Sweet pepper", "Tərəvəz", "2.220", "2.146", "Capsicum annuum L."),
    ("qarpiz", "Qarpız", "Watermelon", "Bostan", "2.224", "2.151", "Citrullus lanatus (T) Mansf"),
    ("yemis", "Yemiş", "Melon", "Bostan", "2.225", "2.152", "Cucumis melo L."),
    ("alma", "Alma", "Apple", "Meyvə", "2.227", "2.154", "Malus domestica Borkh."),
    ("armud", "Armud", "Pear", "Meyvə", "2.228", "2.155", "Pyrus communis L."),
    ("saftali", "Şaftalı", "Peach", "Meyvə", "2.230", "2.157", "Prunus persica (L.) Batsch"),
    ("erik", "Ərik", "Apricot", "Meyvə", "2.231", "2.158", "Prunus armeniaca L."),
    ("gilas", "Gilas", "Sweet cherry", "Meyvə", "2.232", "2.159", "Prunus avium L."),
    ("gavali", "Gavalı", "Plum", "Meyvə", "2.234", "2.161", "Prunus domestica L."),
    ("qoz", "Qoz", "Walnut", "Qoz-fındıq", "2.236", "2.163", "Juglans regia L."),
    ("findiq", "Fındıq", "Hazelnut", "Qoz-fındıq", "2.237", "2.164", "Corylus avellana L."),
    ("badam", "Badam", "Almond", "Qoz-fındıq", "2.238", "2.165", "Prunus amygdalus Batsch."),
    ("nar", "Nar", "Pomegranate", "Meyvə", "2.241", "2.168", "Punica granatum L."),
    ("xurma", "Xurma", "Persimmon", "Meyvə", "2.242", "2.169", "Diospyros kaki L.f."),
    ("encir", "Əncir", "Fig", "Meyvə", "2.243", "2.170", "Ficus carica L."),
    ("zeytun", "Zeytun", "Olive", "Meyvə", "2.244", "2.171", "Olea europaea L."),
    ("limon", "Limon", "Lemon", "Sitrus", "2.250", "2.177", "Citrus limon (L.) Burm. f."),
    ("portagal", "Portağal", "Orange", "Sitrus", "2.251", "2.178", "Citrus sinensis (L.) Osbeck"),
    ("naringi", "Naringi", "Mandarin", "Sitrus", "2.252", "2.179", "Citrus reticulata Blanco x"),
    ("kivi", "Kivi", "Kiwi", "Meyvə", "2.255", "2.182", "Actinidia chinensis Planch."),
    ("uzum", "Üzüm", "Grape", "Üzüm", "2.256", "2.184", "Vitis vinifera L."),
    ("cay", "Çay (yaşıl yarpaq)", "Tea (green leaf)", "Çay", "2.257", "2.185", "Camellia sinensis (L) O.K."),
]

# perennial crops: suitability is judged on the whole year, not a planting window
PERENNIAL = {"Meyvə", "Qoz-fındıq", "Sitrus", "Üzüm", "Çay"}

# autumn-sown cereals: winter months are dormancy (vernalisation), not failure
WINTER = {"bugda", "arpa"}

GROUP_EN = {"Dənli": "Cereals", "Paxlalı": "Pulses", "Texniki": "Industrial", "Tərəvəz": "Vegetables",
            "Bostan": "Melons", "Meyvə": "Fruit", "Qoz-fındıq": "Nuts", "Sitrus": "Citrus", "Üzüm": "Grapes",
            "Çay": "Tea"}
