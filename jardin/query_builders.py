from memoized_property import memoized_property
from datetime import date, datetime


class PGQueryBuilder():

  def __init__(self, **kwargs):
    self.kwargs = kwargs
    self.where_values = None

  @memoized_property
  def model_metadata(self):
    return self.kwargs['model_metadata']

  @memoized_property
  def table_name(self):
    return self.model_metadata['table_name']

  @memoized_property
  def table_alias(self):
    return self.model_metadata['table_alias']

  @memoized_property
  def belongs_to(self):
    return self.model_metadata['belongs_to']

  @memoized_property
  def now(self):
    return datetime.utcnow()

  def extrapolators(self, fields, sep = ', '):
    extrapolators = []
    for field in fields: extrapolators.append('%(' + '%s' % field + ')s')
    return sep.join(extrapolators)

  @staticmethod
  def watermark():
    return " /*[logistics:batching]*/ "

class SelectQueryBuilder(PGQueryBuilder):

  @memoized_property
  def selects(self):
    selects = self.kwargs.get('select', '*')
    if isinstance(selects, str):
      return selects
    elif isinstance(selects, list):
      return ', '.join(selects)

  @memoized_property
  def froms(self):
    if self.table_alias is not None:
      return "%(table_name)s %(table_alias)s" % {'table_name': self.table_name, 'table_alias': self.table_alias}
    else:
      return self.table_name

  @memoized_property
  def wheres(self):
    wheres = self.kwargs.get('where', None)
    if isinstance(wheres, str):
      return wheres
    elif isinstance(wheres, dict):
      self.where_values = wheres
      extrapolators = []
      for field in wheres.keys():
        if isinstance(wheres[field], list) or isinstance(wheres[field], tuple) or isinstance(wheres[field], pd.Series):
          operator = 'IN'
        else: 
          operator = '='
        extrapolators += [field + ' ' + operator + ' %(' + field + ')s']
      return ' AND '.join(extrapolators)
    elif isinstance(wheres, tuple):
      self.where_values = wheres[1]
      return wheres[0]
    elif isinstance(wheres, list):
      res = [self.where_items(where) for where in wheres]
      results = [item for sublist in res for item in sublist]
      return ' AND '.join(results)

  def where_items(self, where):
    results = []
    if isinstance(where, str):
      results += [where]
    elif isinstance(where, dict):
      if self.where_values is None: self.where_values = {}
      for k, v in where.iteritems():
        if isinstance(v, tuple):
          from_label = k + '_from'
          to_label = k + '_to'
          results += [k + ' BETWEEN %(' + from_label + ')s AND %(' + to_label + ')s']
          self.where_values[from_label] = v[0]
          self.where_values[to_label] = v[1]
        else:
          self.where_values[k] = v
          if isinstance(v, list) or isinstance(v, pd.Series):
            operator = 'IN'
          else: 
            operator = '='
          results += [k + ' ' + operator + ' %(' + k + ')s']
    elif isinstance(where, list):
      for k, v in where[1].iteritems(): self.where_values[k] = v
      results += [where[0]]
    return results

  @memoized_property
  def limit(self):
    return self.kwargs.get('limit', None)

  @memoized_property
  def order_bys(self):
    return self.kwargs.get('order', None)

  @memoized_property
  def group_bys(self):
    return self.kwargs.get('group', None)

  @memoized_property
  def left_joins(self):
    joins = self.kwargs.get('left_join', None)
    if joins is None: return
    if isinstance(joins, str): 
      return "LEFT JOIN %s" % joins
    elif isinstance(joins, list):
      return ' '.join(["LEFT JOIN %s" % j for j in joins])

  @memoized_property
  def inner_joins(self):
    joins = self.kwargs.get('inner_join', None)
    if joins is None: return
    if isinstance(joins, str): 
      return "INNER JOIN %s" % joins
    elif isinstance(joins, list):
      js = []
      for j in joins:
        if isinstance(j, str):
          js += ["INNER JOIN %s" % j]
        elif issubclass(j, LogisticsModels):
          js += [self.build_join(j, how = 'INNER')]
      return ' '.join(js)

  def build_join(self, join_model, how = 'INNER'):
    join_model = join_model.model_metadata()
    table_name, join_table_name = self.table_name, join_model['table_name']
    table_alias, join_table_alias = self.table_alias, join_model['table_alias']
    if self.table_name in join_model['belongs_to']:
      foreign_key = join_model['belongs_to'][table_name]
      primary_key = 'id'
    else:
      primary_key = self.model_metadata['belongs_to'][join_table_name]
      foreign_key = 'id'
    return "%(how)s JOIN %(join_table_name)s %(join_table_alias)s ON %(table_alias)s.%(primary_key)s = %(join_table_alias)s.%(foreign_key)s" % {'how': how, 'join_table_name': join_table_name, 'join_table_alias': join_table_alias, 'table_alias': table_alias, 'foreign_key': foreign_key, 'primary_key': primary_key}

  @memoized_property
  def query(self):
    query = self.__class__.watermark() + "SELECT " + self.selects + ' FROM ' + self.froms
    if self.left_joins: query += ' ' + self.left_joins
    if self.inner_joins: query += ' ' + self.inner_joins
    if self.wheres: query += ' WHERE ' + self.wheres
    if self.group_bys: query += ' GROUP BY ' + self.group_bys
    if self.order_bys: query += ' ORDER BY ' + self.order_bys
    if self.limit: query += ' LIMIT ' + str(self.limit)
    query += ';'
    if self.where_values:
      self.prepare_where_values()
      return (query, self.where_values)
    else:
      return (query, )

  def prepare_where_values(self):
    for k, v in self.where_values.iteritems():
      if isinstance(v, pd.Series) or isinstance(v, list):
        self.where_values[k] = tuple(v)

class InsertQueryBuilder(PGQueryBuilder):

  @memoized_property
  def values(self):
    values = self.kwargs['values']
    values['created_at'] = self.now
    values['updated_at'] = self.now
    return values

  @memoized_property
  def field_array(self):
    return self.values.keys()

  @memoized_property
  def fields(self):
    return ', '.join(self.field_array)

  @memoized_property
  def query(self):
    query = self.__class__.watermark() + "INSERT INTO " + self.table_name + " (" + self.fields + ") VALUES (" + self.extrapolators(self.field_array, sep = ', ') + ") RETURNING id;"
    return (query, self.values)

class UpdateQueryBuilder(PGQueryBuilder):

  @memoized_property
  def values(self):
    values = self.kwargs['values']
    values['updated_at'] = self.now
    return values

  @memoized_property
  def fields(self): pass

  @memoized_property
  def query(self):
    query = self.__class__.watermark() + "UPDATE " + self.table_name + " SET " + self.fields
    if self.wheres: query += " WHERE " + self.wheres