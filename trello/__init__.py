from httplib2 import Http
from urllib import urlencode
from datetime import datetime
import exceptions
import json
import oauth2 as oauth
import os
import random
import time
import urlparse

class ResourceUnavailable(Exception):
	"""Exception representing a failed request to a resource"""

	def __init__(self, msg, http_response):
		Exception.__init__(self)
		self._msg = msg
		self._status = http_response.status

	def __str__(self):
		return "Resource unavailable: %s (HTTP status: %s)" % (self._msg, self._status)

class Unauthorized(ResourceUnavailable):
	pass

class TrelloClient(object):
	""" Base class for Trello API access """

	def __init__(self, api_key, token, api_secret = None, token_secret = None):
		"""
		Constructor

		:api_key: API key generated at https://trello.com/1/appKey/generate
		:oauth_token: OAuth token generated by the user
		"""

		if api_key and api_secret and token and token_secret:
			# oauth
			self.oauth_consumer = oauth.Consumer(key = api_key, secret = api_secret)
			self.oauth_token = oauth.Token(key = token, secret = token_secret)
			self.client = oauth.Client(self.oauth_consumer, self.oauth_token)

		elif api_key and token:
			self.client = Http()

		self.api_key = api_key
		self.auth_token = token

	def logout(self):
		"""Log out of Trello. This method is idempotent."""

		# TODO: refactor
		pass
		#if not self._cookie:
			#return

		#headers = {'Cookie': self._cookie, 'Accept': 'application/json'}
		#response, content = self.client.request(
				#'https://trello.com/logout',
				#'GET',
				#headers = headers,
				#)

		## TODO: error checking
		#self._cookie = None

	def build_url(self, path, query = {}):
		"""
		Builds a Trello URL.

		:path: URL path
		:params: dict of key-value pairs for the query string
		"""
		url = 'https://api.trello.com/1'
		if path[0:1] != '/':
			url += '/'
		url += path

		if hasattr(self, 'oauth_token'):
			url += '?'
			url += "key="+self.oauth_token.key
			url += "&token="+self.oauth_consumer.key
		else:
			url += '?'
			url += "key="+self.api_key
			url += "&token="+self.auth_token

		if len(query) > 0:
			url += '&'+urlencode(query)

		return url

	def list_boards(self):
		"""
		Returns all boards for your Trello user

		:return: a list of Python objects representing the Trello boards. Each board has the 
		following noteworthy attributes:
			- id: the board's identifier
			- name: Name of the board
			- desc: Description of the board (optional - may be missing from the returned JSON)
			- closed: Boolean representing whether this board is closed or not
			- url: URL to the board
		"""
		json_obj = self.fetch_json('/members/me/boards/all')
		boards = list()
		for obj in json_obj:
			boards.append(self._board_from_json(obj))

		return boards
	
	def get_board(self, board_id):
		obj = self.fetch_json('/boards/' + board_id)
		return self._board_from_json(obj)

	def get_list(self, list_id):
		obj = self.fetch_json('/lists/' + list_id)
		list = List(self.get_board(obj['idBoard']), obj['id'], name=obj['name'].encode('utf-8'))
		list.closed = obj['closed']
		return list

	def get_member(self, member_id):
		return Member(self, member_id).fetch()

	def fetch_json(
			self,
			uri_path,
			http_method = 'GET',
			headers = {},
			query_params = {},
			post_args = {}):
		""" Fetch some JSON from Trello """

		if http_method in ("POST", "PUT", "DELETE"):
			headers['Content-type'] = 'application/json'

		headers['Accept'] = 'application/json'
		url = self.build_url(uri_path, query_params)
		response, content = self.client.request(
				url,
				http_method,
				headers = headers,
				body = json.dumps(post_args))

		# error checking
		if response.status == 401:
			raise Unauthorized(url)
		if response.status != 200:
			raise ResourceUnavailable(url, response)
		return json.loads(content)

	def _board_from_json(self, json):
		board = Board(self, json['id'], name = json['name'].encode('utf-8'))
		board.description = json.get('desc','').encode('utf-8')
		board.closed = json['closed']
		board.url = json['url']
		return board


class Board(object):
	"""Class representing a Trello board. Board attributes are stored as normal Python attributes;
	access to all sub-objects, however, is always an API call (Lists, Cards).
	"""

	def __init__(self, client, board_id, name=''):
		"""Constructor.

		:trello: Reference to a Trello object
		:board_id: ID for the board
		"""
		self.client = client
		self.id = board_id
		self.name = name

	def __repr__(self):
		return '<Board %s>' % self.name

	def fetch(self):
		"""Fetch all attributes for this board"""
		json_obj = self.client.fetch_json('/boards/'+self.id)
		self.name = json_obj['name'].encode('utf-8')
		self.description = json_obj.get('desc','')
		self.closed = json_obj['closed']
		self.url = json_obj['url']

	def save(self):
		pass

	def all_lists(self):
		"""Returns all lists on this board"""
		return self.get_lists('all')

	def open_lists(self):
		"""Returns all open lists on this board"""
		return self.get_lists('open')

	def closed_lists(self):
		"""Returns all closed lists on this board"""
		return self.get_lists('closed')

	def get_lists(self, list_filter):
		# error checking
		json_obj = self.client.fetch_json(
				'/boards/'+self.id+'/lists',
				query_params = {'cards': 'none', 'filter': list_filter})
		lists = list()
		for obj in json_obj:
			l = List(self, obj['id'], name=obj['name'].encode('utf-8'))
			l.closed = obj['closed']
			lists.append(l)

		return lists

	def add_list(self, name):
		"""Add a card to this list

		:name: name for the card
		:return: the card
		"""
		obj = self.client.fetch_json(
			'/lists',
			http_method = 'POST',
			post_args = {'name': name, 'idBoard': self.id},)
		list = List(self, obj['id'], name=obj['name'].encode('utf-8'))
		list.closed = obj['closed']
		return list 

	def all_cards(self):
		"""Returns all cards on this board"""
		return self.get_cards('all')

	def open_cards(self):
		"""Returns all open cards on this board"""
		return self.get_cards('open')

	def closed_cards(self):
		"""Returns all closed cards on this board"""
		return self.get_cards('closed')

	def get_cards(self, card_filter):
		# error checking
		json_obj = self.client.fetch_json(
				'/boards/'+self.id+'/cards',
				query_params = {'filter': card_filter})
		cards = list()
		for obj in json_obj:
			card = Card(self, obj['id'], name=obj['name'].encode('utf-8'))
			card.closed = obj['closed']
			card.member_ids = obj['idMembers']
			cards.append(card)

		return cards

class List(object):
	"""Class representing a Trello list. List attributes are stored on the object, but access to 
	sub-objects (Cards) require an API call"""

	def __init__(self, board, list_id, name=''):
		"""Constructor

		:board: reference to the parent board
		:list_id: ID for this list
		"""
		self.board = board
		self.client = board.client
		self.id = list_id
		self.name = name

	def __repr__(self):
		return '<List %s>' % self.name

	def fetch(self):
		"""Fetch all attributes for this list"""
		json_obj = self.client.fetch_json('/lists/'+self.id)
		self.name = json_obj['name'].encode('utf-8')
		self.closed = json_obj['closed']

	def list_cards(self):
		"""Lists all cards in this list"""
		json_obj = self.client.fetch_json('/lists/'+self.id+'/cards')
		cards = list()
		for c in json_obj:
			card = Card(self, c['id'], name = c['name'].encode('utf-8'))
			card.description = c.get('desc','').encode('utf-8')
			card.closed = c['closed']
			card.url = c['url']
			card.member_ids = c['idMembers']
			cards.append(card)
		return cards

	def add_card(self, name, desc = None):
		"""Add a card to this list

		:name: name for the card
		:return: the card
		"""
		json_obj = self.client.fetch_json(
				'/lists/'+self.id+'/cards',
				http_method = 'POST',
				post_args = {'name': name, 'idList': self.id, 'desc': desc},)
		card = Card(self, json_obj['id'])
		card.name = json_obj['name']
		card.description = json_obj.get('desc','')
		card.closed = json_obj['closed']
		card.url = json_obj['url']
		card.member_ids = json_obj['idMembers']
		return card
		
	def fetch_actions(self, action_filter):
		"""
		Fetch actions for this list can give more argv to action_filter, 
		split for ',' json_obj is list
		"""
		json_obj = self.client.fetch_json(
				'/lists/'+self.id+'/actions',
				query_params = {'filter': action_filter})
		self.actions = json_obj

class Card(object):
	""" 
	Class representing a Trello card. Card attributes are stored on 
	the object
	"""

	def __init__(self, trello_list, card_id, name=''):
		"""Constructor

		:trello_list: reference to the parent list
		:card_id: ID for this card
		"""
		self.trello_list = trello_list
		self.client = trello_list.client
		self.id = card_id
		self.name = name

	def __repr__(self):
		return '<Card %s>' % self.name

	def fetch(self):
		"""Fetch all attributes for this card"""
		json_obj = self.client.fetch_json(
				'/cards/'+self.id,
				query_params = {'badges': False})
		self.name = json_obj['name'].encode('utf-8')
		self.description = json_obj.get('desc','')
		self.closed = json_obj['closed']
		self.url = json_obj['url']
		self.member_ids = json_obj['idMembers']
		self.short_id = json_obj['idShort']
		self.list_id = json_obj['idList']
		self.board_id = json_obj['idBoard']
		self.labels = json_obj['labels']
		self.badges = json_obj['badges']

	def fetch_actions(self, action_filter='createCard'):
		"""
		Fetch actions for this card can give more argv to action_filter, 
		split for ',' json_obj is list
		"""
		json_obj = self.client.fetch_json(
				'/cards/'+self.id+'/actions',
				query_params = {'filter': action_filter})
		self.actions = json_obj

	@property
	def create_date(self):
		self.fetch_actions()
		date_str = self.actions[0]['date'][:-5]
		return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')

	def set_description(self, description):
		self._set_remote_attribute('desc', description)
		self.description = description

	def set_closed(self, closed):
		self._set_remote_attribute('closed', closed)
		self.closed = closed

	def delete(self):
		# Delete this card permanently
		self.client.fetch_json(
			'/cards/'+self.id,
			http_method = 'DELETE',)

	def assign(self, member_id):
		self.client.fetch_json(
			'/cards/'+self.id+'/members',
			http_method = 'POST',
			post_args = {'value' : member_id, })

	def _set_remote_attribute(self, attribute, value):
		self.client.fetch_json(
			'/cards/'+self.id+'/'+attribute,
			http_method = 'PUT',
			post_args = {'value': value,},)

class Member(object):
	""" 
	Class representing a Trello member.
	"""

	def __init__(self, client, member_id):
		self.client = client
		self.id = member_id

	def __repr__(self):
		return '<Member %s>' % self.id

	def fetch(self):
		"""Fetch all attributes for this card"""
		json_obj = self.client.fetch_json(
				'/members/'+self.id,
				query_params = {'badges': False})
		self.status = json_obj['status'].encode('utf-8')
                self.id = json_obj.get('id','')
		self.bio = json_obj.get('bio','')
		self.url = json_obj.get('url','')
		self.username = json_obj['username'].encode('utf-8')
		self.full_name = json_obj['fullName'].encode('utf-8')
		self.initials = json_obj['initials'].encode('utf-8')
		return self

# vim:noexpandtab
