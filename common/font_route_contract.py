"""Dispatch explicit XML representations without relaxing legacy invariants."""
import minimal_xml_router


def validate_route_plan(plan, font_plan=None):
    if plan.get('schema') == 'fixed-static-xml-route-plan-v1':
        import fixed_static_xml_router
        return fixed_static_xml_router.validate_route_plan(plan, font_plan)
    return minimal_xml_router.validate_route_plan(plan, font_plan)


def render_all(plan, artifact_map, output_root, compiled_bindings=None):
    if plan.get('schema') == 'fixed-static-xml-route-plan-v1':
        import fixed_static_xml_router
        return fixed_static_xml_router.render_all(plan, artifact_map, output_root, compiled_bindings or {})
    return minimal_xml_router.render_all(plan, artifact_map, output_root)
