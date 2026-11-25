"""Matrículas de remolcadores y prácticos y teléfonos importantes (Utilidades -> Números importantes).

Fuente: «REMOLQUES ESTIBA CONTROLES.xlsx» y «MATRICULAS TUGS Y PRACTICOS.xlsx» (noviembre 2026). Son datos fijos: para sumar o corregir uno se edita esta lista.
Las matrículas de los remolcadores van con cinco cifras (03114), como en el listado de matrículas.
"""

# --------------------------------------------------------------------------------------------------------------- remolcadores
# (empresa, remolcador, matrícula). Empresa vacía = el listado no dice de quién es.
REMOLCADORES = [
    ("SVITZER", "SVITZER GRAND BAHAMA", "03011"),
    ("SVITZER", "SVITZER ENDEAVOUR", "03003"),
    ("SVITZER", "SVITZER HONOUR", "03004"),
    ("SVITZER", "SVITZER DAMKA", "03005"),
    ("SVITZER", "SVITZER MORA", "03006"),
    ("SVITZER", "BURONDI", "03010"),
    ("ANTARES", "CICLON", "02037"),
    ("ANTARES", "MAPUCHE I", "02725"),
    ("ANTARES", "PAMPA V", "02642"),
    ("ANTARES", "DIAGUITA", "02779"),
    ("ANTARES", "TEHUELCHE", "02641"),
    ("ANTARES", "TEMPLE", "02512"),
    ("TRANSONA", "ONA PAZ", "03016"),
    ("TRANSONA", "ONA TRIUNFO", "02545"),
    ("CPT", "TIRUA", "03114"),
    ("CPT", "TOCONAO", "03048"),
    ("CPT", "MARIA LUISA", "02915"),
    ("PTO MARIEL (COOPOR)", "COOPOR ESTIBADOR I", "02998"),
    ("PTO MARIEL (COOPOR)", "COOPOR ESTIBADOR II", "02999"),
    ("", "MIRADOR", "02613"),
    ("", "MADRUGADOR", "02356"),
    ("", "ZEUS I", "03007"),
    ("PTO MARIEL (COOPOR)", "CRIOLLO", "02224"),
]

# --------------------------------------------------------------------------------------------------------------- prácticos
# (empresa, práctico, matrícula / credencial, DNI u otros datos)
PRACTICOS = [
    ("DONMAR", "SEBASTIAN, FERNANDO", "1039-3", ""),
    ("DONMAR", "ARCHERRIZO, EDUARDO", "1194-1", ""),
    ("DONMAR", "DOÑA, EDUARDO", "1222-7", ""),
    ("DONMAR", "GOMEZ BERET, SANTIAGO", "1223-6", ""),
    ("DONMAR", "MARCHESI, SERGIO", "1239-9", ""),
    ("DONMAR", "PUYAT, MARTIN", "1330-4", ""),
    ("DONMAR", "ABALO RAINOLTER, HORACIO MARCELO", "1327-4", ""),
    ("DONMAR", "LOPEZ OBIOL, MAXIMILIANO PABLO", "1548", ""),
    ("DONMAR", "ALBINARRATE, FABIO", "1511", ""),
    ("DONMAR", "GALAN NUÑEZ, GABRIEL ALEJANDRO", "1584", ""),
    ("DONMAR", "GOMEZ, MATIAS EZEQUIEL", "1640", ""),
    ("ESEM", "ALMADA, GUSTAVO HONORIO", "1221-3", "DNI 13.754.420"),
    ("ESEM", "CASTAGNOLA, ANDRES", "1005-4", "DNI 13.431.355"),
    ("ESEM", "FERNANDEZ, JORGE", "1280-4", "DNI 13.641.005"),
    ("ESEM", "KOCSIS, ANDRES FLAVIO ORESTE", "1250-0", "DNI 18.607.128"),
    ("ESEM", "PERARNAU, MILTON GABRIEL", "1004-8", "C.I. 6.229.154 · DNI 8.637.433"),
    ("ESEM", "GIGENA, FLAVIO JESUS", "1426-0", "DNI 24.635.864"),
    ("ESEM", "MALLIMACCI, HUGO FERNANDO", "1430-7", "DNI 24.695.370"),
    ("ESEM", "LLOUSAS, DANIEL EDUARDO", "1473", "DNI 11.893.295"),
    ("ESEM", "ALVAREZ, JULIAN ROBERTO", "1528", "DNI 23.265.740"),
    ("", "BONASTRE, FELIPE", "1621", ""),
    ("", "ARANCIBIA, STELLA MARIS", "1593", ""),
]

# Qué empresa de práctico usa cada cliente.
PRACTICO_POR_CLIENTE = [
    ("ARGELAN", "ESEM"), ("ATLAS MARITIME", "ESEM"), ("B&G", "ESEM"), ("B2B", "ESEM"), ("BLUESTAR", "DONMAR"), ("ECSA", "ESEM"),
    ("HEINLEIN", "ESEM"), ("MARITIMA PAMPA", "ESEM"), ("OCEANWAY", "ESEM"), ("SERVICES MANAGMENT", "ESEM"), ("SEVEN SEAS", "ESEM"),
    ("T&T", "DONMAR"), ("ABBEY SEA", "ESEM"), ("SEA PLATE", "DONMAR"), ("WBL", "DONMAR"),
]

# --------------------------------------------------------------------------------------------------------------- teléfonos
# (empresa de control, contacto, teléfono)
CONTROLES = [
    ("CIS CONTROL", "Héctor Susca", "2915038260"),
    ("ISB", "Héctor Susca", "2915038260"),
    ("EUROAMERICA", "Héctor Susca", "2915038260"),
    ("TRUST", "Gonza Acosta", "2915100371"),
    ("AMSPEC", "Gonza Acosta", "2915100371"),
    ("INTERTEK", "Mateo Mart.", "2915042538"),
    ("SGS", "Hernán", "2914059069"),
    ("RRMG", "Leo López", "2915724883"),
    ("OPER AGRO", "Marcos Chiesa", "3415313727"),
    ("COTECNA", "Ale Monges", "2915037000"),
    ("CONTROL UNION", "René Bascal", "2915011486"),
]

TERMINALES = [
    ("CARGILL", "Claudio Iriarte", "2914477455"),
    ("ADM", "Ariel Copreni", "2916429160"),
    ("TBB 9", "Marcelo Barbieri", "2915057423"),
    ("VITERRA", "Fede Nastasi", "2316400133"),
    ("LDC", "Tomás Pariente", "2915164049"),
]

ESTIBA = [
    ("Bochi Alvarez", "2915718103"),
    ("Maxi Garay", "2915358496"),
    ("Fer Navarrete", "2914237825"),
    ("Bruno Aceituno", "2915036860"),
    ("Juan Penessi", "2915703260"),
    ("Fer Nuñez", "2916494377"),
    ("Juan Cacheiro", "2914278078"),
]

DRAFT = [
    ("Manu De Luca", "2914491165"),
    ("Juan Giambelluca", "2915762857"),
    ("Adrián Gutiérrez", "2916483697"),
    ("Rubén Merigo", "2914055359"),
    ("Maxi Metz", "2914023363"),
    ("Joaquín Guelfi", "2914026313"),
]

# --------------------------------------------------------------------------------------------------------------- notas
# Anotaciones para SIG Bodegas: cómo se llama cada mercadería en el sistema.
SIG_BODEGAS = [
    ("DURO", "GRANO TRIGO"),
    ("CEREAL", "MAIZ"),
    ("GRANO DE SOJA", "SOJA"),
    ("MALTA", "MALTA"),
    ("GRANO DE CEBADA", "CEBADA"),
]
