{{- define "todomvc.image" -}}
{{- $tag := .root.Values.image.tag | default .root.Chart.AppVersion -}}
{{- if eq $tag "unset" -}}
{{- fail "no image tag: set image.tag, or package the chart with --app-version <commit>" -}}
{{- end -}}
{{ .root.Values.image.registry }}/{{ .name }}:{{ $tag }}
{{- end }}

{{- define "todomvc.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end }}
