locals {
  rules_dir = "${path.module}/../rules"

  # Every rules/*.yaml file except the ones starting with "_" (like _template.yaml).
  rule_files = [for f in fileset(local.rules_dir, "*.yaml") : f if !startswith(f, "_")]

  raw_rules = [for f in local.rule_files : merge(yamldecode(file("${local.rules_dir}/${f}")), { _file = f })]

  # Normalise each rule to one shape and fill in defaults.
  # Duplicate ids fail here with a "duplicate object key" error.
  rules = {
    for r in local.raw_rules : r.id => {
      file                 = r._file
      kind                 = lower(try(r.kind, "scheduled"))
      display_name         = r.display_name
      description          = try(r.description, null)
      severity             = try(r.severity, "Medium")
      enabled              = try(r.enabled, true)
      query                = r.query
      query_frequency      = try(r.query_frequency, "PT1H")
      query_period         = try(r.query_period, "PT1H")
      trigger_operator     = try(r.trigger_operator, "GreaterThan")
      trigger_threshold    = try(r.trigger_threshold, 0)
      suppression_enabled  = try(r.suppression_enabled, false)
      suppression_duration = try(r.suppression_duration, "PT5H")
      tactics              = try(r.tactics, [])
      techniques           = try(r.techniques, [])
      create_incident      = try(r.create_incident, true)
      group_incidents      = try(r.group_incidents, false)
      entities = [
        for e in try(r.entities, []) : {
          type   = e.type
          fields = [for fm in e.fields : { identifier = fm.identifier, column = fm.column }]
        }
      ]
    }
  }

  scheduled_rules = { for id, r in local.rules : id => r if r.kind == "scheduled" }
  nrt_rules       = { for id, r in local.rules : id => r if r.kind == "nrt" }
}

check "rule_kinds" {
  assert {
    condition     = length(local.rules) == length(local.scheduled_rules) + length(local.nrt_rules)
    error_message = "Every rule needs kind: scheduled or kind: nrt. Check: ${join(", ", [for id, r in local.rules : r.file if !contains(["scheduled", "nrt"], r.kind)])}"
  }
}

resource "azurerm_sentinel_alert_rule_scheduled" "rule" {
  for_each = local.scheduled_rules

  name                       = each.key
  log_analytics_workspace_id = azurerm_sentinel_log_analytics_workspace_onboarding.sentinel.workspace_id
  display_name               = each.value.display_name
  description                = each.value.description
  severity                   = each.value.severity
  enabled                    = each.value.enabled
  query                      = each.value.query
  query_frequency            = each.value.query_frequency
  query_period               = each.value.query_period
  trigger_operator           = each.value.trigger_operator
  trigger_threshold          = each.value.trigger_threshold
  suppression_enabled        = each.value.suppression_enabled
  suppression_duration       = each.value.suppression_duration
  tactics                    = each.value.tactics
  techniques                 = each.value.techniques

  incident {
    create_incident_enabled = each.value.create_incident
    grouping {
      enabled                = each.value.group_incidents
      lookback_duration      = "PT5H"
      entity_matching_method = "AllEntities"
    }
  }

  dynamic "entity_mapping" {
    for_each = each.value.entities
    content {
      entity_type = entity_mapping.value.type
      dynamic "field_mapping" {
        for_each = entity_mapping.value.fields
        content {
          identifier  = field_mapping.value.identifier
          column_name = field_mapping.value.column
        }
      }
    }
  }

  # Wait for the Activity log connection so AzureActivity exists.
  depends_on = [azurerm_monitor_diagnostic_setting.activity_log]
}

resource "azurerm_sentinel_alert_rule_nrt" "rule" {
  for_each = local.nrt_rules

  name                       = each.key
  log_analytics_workspace_id = azurerm_sentinel_log_analytics_workspace_onboarding.sentinel.workspace_id
  display_name               = each.value.display_name
  description                = each.value.description
  severity                   = each.value.severity
  enabled                    = each.value.enabled
  query                      = each.value.query
  suppression_enabled        = each.value.suppression_enabled
  suppression_duration       = each.value.suppression_duration
  tactics                    = each.value.tactics
  techniques                 = each.value.techniques

  event_grouping {
    aggregation_method = "SingleAlert"
  }

  incident {
    create_incident_enabled = each.value.create_incident
    grouping {
      enabled                = each.value.group_incidents
      lookback_duration      = "PT5H"
      entity_matching_method = "AllEntities"
    }
  }

  dynamic "entity_mapping" {
    for_each = each.value.entities
    content {
      entity_type = entity_mapping.value.type
      dynamic "field_mapping" {
        for_each = entity_mapping.value.fields
        content {
          identifier  = field_mapping.value.identifier
          column_name = field_mapping.value.column
        }
      }
    }
  }

  depends_on = [azurerm_monitor_diagnostic_setting.activity_log]
}
