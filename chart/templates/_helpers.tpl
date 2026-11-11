{{- define "digit-classifier.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
{{- end }}

{{- define "digit-classifier.labels" -}}
{{ include "digit-classifier.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}
