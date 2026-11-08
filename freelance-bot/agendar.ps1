# Registra duas tarefas no Agendador de Tarefas do Windows (usuário atual, sem admin):
#   1. "FreelanceBot - Rodada": roda o orquestrador a cada 2 horas
#   2. "FreelanceBot - Painel": inicia o painel local ao fazer logon
# Uso:   powershell -ExecutionPolicy Bypass -File agendar.ps1
# Remover: powershell -ExecutionPolicy Bypass -File agendar.ps1 -Remover

param([switch]$Remover, [int]$IntervaloHoras = 2)

$pasta = $PSScriptRoot
$nomes = @("FreelanceBot - Rodada", "FreelanceBot - Painel")

if ($Remover) {
    foreach ($n in $nomes) { Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue }
    Write-Host "Tarefas removidas."
    return
}

$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)

$acaoRodada = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$pasta\orquestrador.py`"" -WorkingDirectory $pasta
$gatilhoRodada = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervaloHoras)
Register-ScheduledTask -TaskName $nomes[0] -Action $acaoRodada -Trigger $gatilhoRodada -Settings $config `
    -Description "Busca e avalia projetos freelance" -Force | Out-Null

$configPainel = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$acaoPainel = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$pasta\painel\servidor.py`"" -WorkingDirectory $pasta
$gatilhoPainel = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName $nomes[1] -Action $acaoPainel -Trigger $gatilhoPainel -Settings $configPainel `
    -Description "Painel local do Freelance bot (http://127.0.0.1:5000)" -Force | Out-Null
Start-ScheduledTask -TaskName $nomes[1]

Write-Host "Tarefas registradas. Primeira rodada em ~1 minuto; depois a cada $IntervaloHoras h."
Write-Host "Painel: http://127.0.0.1:5000   Logs: $pasta\logs"
