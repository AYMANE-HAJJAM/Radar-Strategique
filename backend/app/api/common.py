from flask import jsonify, request


def error(code, message, status):
    return jsonify(error={'code': code, 'message': message}), status


def pagination_args():
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
    except ValueError as exc:
        raise ValueError('page et page_size doivent être des entiers.') from exc
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError('Pagination invalide.')
    return page, page_size


def paginated(items, page, page_size, total):
    return {'items': items, 'page': page, 'page_size': page_size, 'total': total,
            'pages': max(1, (total + page_size - 1) // page_size)}


def run_json(run):
    fields = ('id', 'radar_id', 'agent_name', 'status', 'current_stage', 'trigger_type', 'triggered_by',
              'candidates_count', 'duplicate_count', 'analyzed_count', 'new_results_count',
              'updated_results_count', 'rejected_count', 'input_tokens', 'output_tokens', 'ai_calls',
              'error_kind', 'error_message', 'run_metadata')
    result = {field: getattr(run, field) for field in fields}
    for field in ('started_at', 'finished_at'):
        value = getattr(run, field)
        result[field] = value.isoformat() if value else None
    result['estimated_ai_cost'] = str(run.estimated_ai_cost) if run.estimated_ai_cost is not None else None
    result['stage_history'] = run.stage_history
    launcher = run.launcher
    result['launched_by'] = None if launcher is None else {'id': launcher.id, 'name': launcher.display_name}
    return result
