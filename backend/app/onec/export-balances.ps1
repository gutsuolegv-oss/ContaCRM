<#
ContaCRM: exportul soldurilor clienților din 1C (baza de tip fișier) spre CRM.

Rulează pe calculatorul Windows unde e instalat 1C:Enterprise 8.3 și unde se află baza.
Se conectează la bază prin COM (V83.COMConnector), fără publicare pe web, calculează soldul
fiecărui contragent pe contul de creanțe (implicit 221) și îl trimite în CRM.

Utilizare:
  .\export-balances.ps1              # prima dată: creează config.json lângă script
  .\export-balances.ps1 -Descopera   # listează registrele, planurile de conturi și câmpurile
                                     # contragentului (doar nume, fără date), ca să potrivim config.json
  .\export-balances.ps1 -Proba       # calculează soldurile și le afișează, fără să le trimită
  .\export-balances.ps1              # calculează și trimite în CRM

Cerințe:
  - COM-connectorul înregistrat o dată, ca administrator:
      regsvr32 "C:\Program Files\1cv8\<versiunea>\bin\comcntr.dll"
  - PowerShell de aceeași arhitectură ca 1C: pentru 1C pe 32 de biți, rulează scriptul cu
      C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe
  - un utilizator 1C doar pentru citire (conexiunea COM folosește o licență 1C cât rulează).

config.json conține parola 1C și cheia CRM: păstrează-l doar pe acest calculator, cu acces
restrâns (ex. doar contul care rulează sarcina programată).
#>
param(
    [switch]$Descopera,
    [switch]$Proba,
    [string]$Config = (Join-Path $PSScriptRoot "config.json")
)

$ErrorActionPreference = "Stop"
$ScriptVersion = "1"

# --- configurarea ---

if (-not (Test-Path $Config)) {
    $template = [ordered]@{
        base_path          = "C:\1C\Baza_test"
        user               = "crm_citire"
        password           = ""
        crm_url            = "http://192.168.100.101:5173"
        api_key            = "1c_..."
        register           = "Хозрасчетный"
        chart_of_accounts  = "Хозрасчетный"
        account_code       = "221"
        counterparty_index = 1
        catalog            = "Контрагенты"
        idno_attribute     = "ФискальныйКод"
    }
    $template | ConvertTo-Json | Set-Content -Path $Config -Encoding UTF8
    Write-Host "Am creat $Config. Completează base_path, user, password, crm_url și api_key,"
    Write-Host "apoi rulează scriptul cu -Descopera ca să verificăm numele din configurația 1C."
    exit 1
}
$cfg = Get-Content -Path $Config -Raw -Encoding UTF8 | ConvertFrom-Json
if ($env:ONEC_PASSWORD) { $cfg.password = $env:ONEC_PASSWORD }

# --- conexiunea la 1C ---

function Connect-OneC {
    try {
        $connector = New-Object -ComObject "V83.COMConnector"
    } catch {
        throw "V83.COMConnector nu e înregistrat (regsvr32 comcntr.dll ca administrator) sau PowerShell are altă arhitectură decât 1C (32/64 de biți)."
    }
    $conn = 'File="{0}";Usr="{1}";Pwd="{2}";' -f $cfg.base_path, $cfg.user, $cfg.password
    return $connector.Connect($conn)
}

function Invoke-Query($onec, [string]$text, [hashtable]$params = @{}) {
    <# Rândurile interogării, fiecare ca listă de valori (în ordinea coloanelor). #>
    $query = $onec.NewObject("Query")
    $query.Text = $text
    foreach ($name in $params.Keys) { $query.SetParameter($name, $params[$name]) }
    $result = $query.Execute()
    $columns = $result.Columns.Count()
    $selection = $result.Select()
    $rows = @()
    while ($selection.Next()) {
        $values = @()
        for ($i = 0; $i -lt $columns; $i++) { $values += , $selection.Get($i) }
        $rows += , $values
    }
    # virgula: altfel PowerShell „despachetează” un rezultat cu un singur rând
    return , $rows
}

function Text($onec, $value) { if ($null -eq $value) { "" } else { $onec.String($value) } }

$onec = Connect-OneC

# --- modul -Descopera: doar nume de obiecte, fără date ---

if ($Descopera) {
    Write-Host "== Registre contabile (register) și planul lor de conturi (chart_of_accounts)"
    $registers = $onec.Metadata.AccountingRegisters
    for ($i = 0; $i -lt $registers.Count(); $i++) {
        $r = $registers.Get($i)
        Write-Host ("  {0}  [{1}]  plan de conturi: {2}" -f $r.Name, (Text $onec $r.Synonym), $r.ChartOfAccounts.Name)
    }
    Write-Host "== Cataloage de contragenți (catalog) și câmpurile lor (idno_attribute)"
    $catalogs = $onec.Metadata.Catalogs
    for ($i = 0; $i -lt $catalogs.Count(); $i++) {
        $c = $catalogs.Get($i)
        if ($c.Name -notmatch "Контраг|Contrag|Partener|Партнер") { continue }
        Write-Host ("  {0}  [{1}]" -f $c.Name, (Text $onec $c.Synonym))
        $attrs = $c.Attributes
        for ($j = 0; $j -lt $attrs.Count(); $j++) {
            $a = $attrs.Get($j)
            $mark = if ($a.Name + (Text $onec $a.Synonym) -match "(?i)фиск|fiscal|idno|инн|код") { "  <== cod fiscal?" } else { "" }
            Write-Host ("      {0}  [{1}]{2}" -f $a.Name, (Text $onec $a.Synonym), $mark)
        }
    }
    Write-Host ("== Contul {0} în planul {1}: subcontourile (counterparty_index = numărul contragentului)" -f $cfg.account_code, $cfg.chart_of_accounts)
    $rows = Invoke-Query $onec @"
ВЫБРАТЬ Т.Ссылка.Код, Т.Ссылка.Наименование, Т.НомерСтроки, ПРЕДСТАВЛЕНИЕ(Т.ВидСубконто)
ИЗ ПланСчетов.$($cfg.chart_of_accounts).ВидыСубконто КАК Т
ГДЕ Т.Ссылка.Код ПОДОБНО &Код
УПОРЯДОЧИТЬ ПО Т.Ссылка.Код, Т.НомерСтроки
"@ @{ "Код" = "$($cfg.account_code)%" }
    foreach ($r in $rows) { Write-Host ("  {0} {1}: subconto {2} = {3}" -f $r[0], $r[1], $r[2], $r[3]) }
    if ($rows.Count -eq 0) { Write-Host "  (niciun cont cu acest cod: verifică chart_of_accounts și account_code)" }
    exit 0
}

# --- soldurile ---

$account = Invoke-Query $onec "ВЫБРАТЬ ПЕРВЫЕ 1 ПС.Ссылка ИЗ ПланСчетов.$($cfg.chart_of_accounts) КАК ПС ГДЕ ПС.Код = &Код" @{ "Код" = [string]$cfg.account_code }
if ($account.Count -eq 0) { throw "Contul $($cfg.account_code) nu există în planul $($cfg.chart_of_accounts)." }

$n = [int]$cfg.counterparty_index
$today = (Get-Date).Date
$rows = Invoke-Query $onec @"
ВЫБРАТЬ
    ПРЕДСТАВЛЕНИЕ(Остатки.Субконто$n) КАК Наименование,
    ВЫРАЗИТЬ(Остатки.Субконто$n КАК Справочник.$($cfg.catalog)).$($cfg.idno_attribute) КАК IDNO,
    СУММА(ЕСТЬNULL(Остатки.СуммаОстатокДт, 0)) КАК Дебет,
    СУММА(ЕСТЬNULL(Остатки.СуммаОстатокКт, 0)) КАК Кредит
ИЗ
    РегистрБухгалтерии.$($cfg.register).Остатки(&Дата, Счет В ИЕРАРХИИ (&Счет), , ) КАК Остатки
СГРУППИРОВАТЬ ПО
    Остатки.Субконто$n
"@ @{ "Дата" = $today.AddDays(1); "Счет" = $account[0][0] }

$payload = [ordered]@{
    as_of          = $today.ToString("yyyy-MM-dd")
    base           = Split-Path $cfg.base_path -Leaf
    script_version = $ScriptVersion
    rows           = @(
        foreach ($r in $rows) {
            $debit = [decimal]$r[2]
            $credit = [decimal]$r[3]
            if ($debit -eq 0 -and $credit -eq 0) { continue }
            [ordered]@{
                idno   = ([string]$r[1]).Trim()
                name   = ([string]$r[0]).Trim()
                debit  = [math]::Round($debit, 2)
                credit = [math]::Round($credit, 2)
            }
        }
    )
}
$json = $payload | ConvertTo-Json -Depth 4 -Compress

if ($Proba) {
    Write-Host ("{0} contragenți cu sold la {1}:" -f $payload.rows.Count, $payload.as_of)
    $payload.rows | Select-Object -First 20 | ForEach-Object {
        Write-Host ("  {0,-13} {1,-40} datorie {2,12:N2}  avans {3,10:N2}" -f $_.idno, $_.name, $_.debit, $_.credit)
    }
    exit 0
}

$response = Invoke-RestMethod -Method Post -Uri ($cfg.crm_url.TrimEnd("/") + "/api/onec/balances") `
    -Headers @{ Authorization = "Bearer $($cfg.api_key)" } `
    -ContentType "application/json; charset=utf-8" `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($json))
Write-Host ("Trimis: {0} contragenți, {1} potriviți cu clienții din CRM, {2} negăsiți." -f $response.rows, $response.matched, $response.unmatched)
