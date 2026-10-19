# Resultado de las pruebas automatizadas

Fecha: **2026-10-19 10:58** · Total: **54** · Exitosas: **54** · Fallidas: **0** · Duración: **48 s**

![Resultado de las pruebas](resultado-pruebas.png)

| Archivo | Qué prueba | Pruebas | Exitosas | Fallidas | Tiempo |
|---|---|---|---|---|---|
| `test_console_logs.py` | Consola y logs | 6 | 6 | 0 | 0.6 s |
| `test_system_runner.py` | Autopruebas y programador | 9 | 9 | 0 | 2.6 s |
| `test_qa_center.py` | API: análisis, resultados, novedades, reportes | 21 | 21 | 0 | 3.5 s |
| `test_testdocs.py` | API: plan, casos, evidencias, trazabilidad, defectos | 7 | 7 | 0 | 1.1 s |
| `test_selenium_ui.py` | E2E con Selenium (navegador real) | 11 | 11 | 0 | 37.8 s |

## Consola y logs (`test_console_logs.py`)

| Prueba | Resultado | Tiempo |
|---|---|---|
| `test_failed_login_emits_warning_record_via_log_handler` | ✅ Exitosa | 0.20 s |
| `test_failed_login_log_line_has_exact_format` | ✅ Exitosa | 0.14 s |
| `test_failed_login_with_unknown_user_is_logged` | ✅ Exitosa | 0.00 s |
| `test_failed_login_writes_warning_to_console` | ✅ Exitosa | 0.14 s |
| `test_protected_endpoint_without_token_logs_unauthorized_access` | ✅ Exitosa | 0.00 s |
| `test_successful_login_does_not_log_failed_attempt` | ✅ Exitosa | 0.14 s |

## Autopruebas y programador (`test_system_runner.py`)

| Prueba | Resultado | Tiempo |
|---|---|---|
| `test_execute_endpoint_requires_token` | ✅ Exitosa | 0.19 s |
| `test_execute_endpoint_runs_batch_as_current_user` | ✅ Exitosa | 0.54 s |
| `test_failed_case_is_recorded_with_detail` | ✅ Exitosa | 0.01 s |
| `test_metrics_include_automation_status_and_last_batch` | ✅ Exitosa | 0.51 s |
| `test_register_manual_run` | ✅ Exitosa | 0.02 s |
| `test_register_manual_run_validation` | ✅ Exitosa | 0.01 s |
| `test_run_system_tests_all_cases_pass_and_are_registered` | ✅ Exitosa | 0.53 s |
| `test_runner_rejects_concurrent_batches` | ✅ Exitosa | 0.00 s |
| `test_scheduler_runs_batch_automatically` | ✅ Exitosa | 0.83 s |

## API: análisis, resultados, novedades, reportes (`test_qa_center.py`)

| Prueba | Resultado | Tiempo |
|---|---|---|
| `test_automatic_report_generation` | ✅ Exitosa | 0.33 s |
| `test_bulk_actions_and_export` | ✅ Exitosa | 0.23 s |
| `test_dashboard_has_all_menus` | ✅ Exitosa | 0.03 s |
| `test_developer_crud` | ✅ Exitosa | 0.06 s |
| `test_executive_report_includes_incidents_and_scans` | ✅ Exitosa | 0.08 s |
| `test_import_junit_xml` | ✅ Exitosa | 0.01 s |
| `test_import_newman_json` | ✅ Exitosa | 0.07 s |
| `test_import_rejects_postman_collection_and_garbage` | ✅ Exitosa | 0.00 s |
| `test_incident_crud_history_and_comments` | ✅ Exitosa | 0.07 s |
| `test_metrics_include_incidents_and_scans` | ✅ Exitosa | 0.01 s |
| `test_new_endpoints_require_token` | ✅ Exitosa | 0.01 s |
| `test_notify_by_webhook` | ✅ Exitosa | 2.13 s |
| `test_notify_without_channels_and_manual_share` | ✅ Exitosa | 0.05 s |
| `test_registered_run_edit_and_delete` | ✅ Exitosa | 0.04 s |
| `test_run_failures_become_incident` | ✅ Exitosa | 0.03 s |
| `test_scan_creates_incidents_without_duplicates` | ✅ Exitosa | 0.23 s |
| `test_scan_endpoint_validates_input` | ✅ Exitosa | 0.00 s |
| `test_scan_report_pdf_and_excel` | ✅ Exitosa | 0.10 s |
| `test_scan_unreachable_url_is_reported` | ✅ Exitosa | 0.02 s |
| `test_settings_validation_and_secret_masking` | ✅ Exitosa | 0.01 s |
| `test_target_crud_and_validation` | ✅ Exitosa | 0.03 s |

## API: plan, casos, evidencias, trazabilidad, defectos (`test_testdocs.py`)

| Prueba | Resultado | Tiempo |
|---|---|---|
| `test_case_lifecycle_execution_defect_and_evidence` | ✅ Exitosa | 0.63 s |
| `test_dashboard_metrics_and_menus` | ✅ Exitosa | 0.03 s |
| `test_defect_reports` | ✅ Exitosa | 0.20 s |
| `test_endpoints_require_token` | ✅ Exitosa | 0.00 s |
| `test_plan_crud_and_validation` | ✅ Exitosa | 0.05 s |
| `test_requirements_crud` | ✅ Exitosa | 0.05 s |
| `test_rtm_report_and_uncovered_requirements` | ✅ Exitosa | 0.14 s |

## E2E con Selenium (navegador real) (`test_selenium_ui.py`)

| Prueba | Resultado | Tiempo |
|---|---|---|
| `test_01_full_flow_login_dashboard_export_logout` | ✅ Exitosa | 4.51 s |
| `test_02_invalid_credentials_show_error_message` | ✅ Exitosa | 0.77 s |
| `test_03_dashboard_without_token_redirects_to_login` | ✅ Exitosa | 0.19 s |
| `test_04_table_filter_by_status` | ✅ Exitosa | 0.99 s |
| `test_05_register_manual_run_from_form` | ✅ Exitosa | 1.50 s |
| `test_06_register_manual_run_validation` | ✅ Exitosa | 1.25 s |
| `test_07_edit_and_delete_registered_result` | ✅ Exitosa | 2.76 s |
| `test_08_scan_url_detects_console_errors` | ✅ Exitosa | 6.70 s |
| `test_09_incident_crud_from_dialog` | ✅ Exitosa | 3.55 s |
| `test_10_test_documentation_flow` | ✅ Exitosa | 5.55 s |
| `test_11_all_menus_without_console_errors` | ✅ Exitosa | 10.05 s |

Archivo JUnit para herramientas de CI: [`junit.xml`](junit.xml)
