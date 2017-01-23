import discord                            # interface and connect with Discord
import asyncio                            # perform functions asynchronously 
import logging                            # log some stuff
import re                                 # regex
import requests                           # do some stuff on the interwebs
import random                             # RNG
from configparser import SafeConfigParser # easy file parsing for the secret token and potentially more options (card page size?)
from bs4 import BeautifulSoup             # parse all of the html
from mtgsdk import Card                   # interface with Gatherer through the existing mtgsdk
from mtgsdk import Set

# only show initial Discord connection info
logging.basicConfig(level=logging.INFO)

# set up the Discord connection object
client = discord.Client()

# bot strings
help = 'My command operator is the ! character.\r\nhelp: Displays this message\r\nsuperhelp: shows a list of all properties that may be used in a search query\r\ntest: Make sure I\'m alive!\r\nTo fetch a card, use double square brackets.\r\nYou can gather card information and an image by using its exact name, or you can search cards with a search term.\r\nBy default, the most recent printing of a card is displayed, but if there are multiple prints, the sets will be listed underneath the card. If you would like info on an older print, include the set code immediately following the double brackets.\r\nsearch: Uses parameters that you input to search all MTG cards. Split each property using the semicolon character (;).\r\nSome properties can take lists. Use a comma (,) to signify AND. Use a pipe (|) to signify OR.\r\nPower, toughness, CMC and loyalty can use the following operators: gt (greater than), lt (less than), gte (greater than or equal to), lte (less than or equal to).\r\nEx. !search set=KLD;rarity=uncommon;color=blue,white;cmc=gte3\r\nUse the superhelp command to list all possible properties.\r\nbooster: Generate a booster pack of a desired set code. Ex. !booster KLD\r\nWhen a search query returns multiple cards, a specific card can be called using the command operator followed by a number.'

superhelp = 'The following properties can be used in a search. Properties with an (L) can be used as lists. Power, toughness, CMC and loyalty may use the operators defined in the regular help.\r\nlayout (L), cmc, colors (L), colorIdentity (L), type (L), supertypes (L), types (L), subtypes (L), rarity (L), set (L), setName (L), text (L), flavor (L), artist (L), power, toughness, loyalty, gameFormat, legality, orderBy'

# global variables
tempCardList = [] # this is used when multiple card matches are found. We use this to call cards by their index, and to paginate lists of cards to keep down the spam
tempCardFlip = '' # this is to store the name of the reverse side of the card in the case of flippable cards
itemsShown = 0    # this is used to store the current 'page' of cards listed in increments of 25
secrettoken = ''  # this is the token the Discord client uses to authenticate and know which server it's going to, this is read in from the config.ini file

# when the bot is initiated we use this event to perform startup activities - currently just for logging
@client.event
@asyncio.coroutine
def on_ready():
	print('Logged in as')
	print(client.user.name)
	print(client.user.id)
	print('------')
	print(client)	
	yield from client.change_presence(game=discord.Game(name='Hearthstone'))

# this event is triggered whenever a message is sent - we look for the command operators and perform actions based on user input
@client.event
@asyncio.coroutine
def on_message(message):
	
	# ensure the bot is alive and not busy performing a request
	if message.content.startswith('!test'):
		yield from client.send_message(message.channel, 'I\'m alive!')
		
	# display the help string
	elif message.content.startswith('!help'):
		yield from client.send_message(message.channel, help)
		
	# display the superhelp string
	elif message.content.startswith('!superhelp'):
		yield from client.send_message(message.channel, superhelp)
		
	# tell the bot what to show it is playing
	elif message.content.startswith('!play '):
		gamename = message.content.split('!play ')
		if(len(gamename) > 1):
			yield from client.change_presence(game=discord.Game(name=gamename[1]))
			
	# look for the [[]] notation to list a card using either its exact name or a search term for multiple cards
	elif '[[' in message.content:											
		cardname = re.findall(r"[[^[]*\[([^]]*)\]]", message.content) # regex matches the text in between [[ and ]]		
		if len(cardname) > 0:
			userset = message.content.split(']]') # look for a setcode following the card notation Ex. [[Doom Blade]]M10
			if userset[1]: # search card name and set code				
				toSend = findCardsByName(cardname[0], userset[1])
				if toSend.startswith('Single match'): # if we put in a partial card name that only returns one result, we need to display the result. We rely on the pipe character to separate the full card name and the set code 
					toSend = findCardsByName(toSend.split('|')[1], toSend.split('|')[2])					
					yield from client.send_message(message.channel, toSend)
				else:
					yield from client.send_message(message.channel, toSend)
			else: # search card name only
				toSend = findCardsByName(cardname[0])
				if toSend.startswith('Single match'): # I don't like this. It's messy and relies on a string output. If a card ever has a pipe in the name, we're screwed
					toSend = findCardsByName(toSend.split('|')[1], toSend.split('|')[2])					
					yield from client.send_message(message.channel, toSend)
				else:				
					yield from client.send_message(message.channel, toSend)
	
	# show the result of the opposite side of a flip or meld card without the user having to type it explicitly
	elif message.content.startswith('!flip'):
		if tempCardFlip:
			toSend = findCardsByName(tempCardFlip)			
			yield from client.send_message(message.channel, toSend)
		else:
			yield from client.send_message(message.channel, 'No flippable card.')
	
	# parse a user's advanced search query. Use the mtgsdk to retrieve a list of cards Ex. !search set=KLD;rarity=uncommon;color=blue,white;cmc=gte3
	elif message.content.startswith('!search '):		
		searchterms = message.content.split('!search ')		
		if (len(searchterms) > 1):
			toSend = advancedSearch(searchterms[1])
			toSend = toSend[:toSend.rfind(',')] # need to find a more consistent way to do this
			yield from client.send_message(message.channel, toSend)		

	# crack open a booster and see what you get! Uses the built in mtgsdk booster function which may or may not be flawed like in the case of SOI (only generates 13-14 cards) Ex. !booster KLD
	elif message.content.startswith('!booster '):
		setcode = message.content.split('!booster ')
		if(len(setcode) > 1):			
			toSend = openBooster(setcode[1])
			toSend = toSend[:toSend.rfind(',')]
			yield from client.send_message(message.channel, toSend)						
	
	# if the user uses a number following the command operator, this means they want to retrieve the card at a certain index in a list of cards 	
	elif len(re.findall(r"![0-9]{1,3}", message.content)) > 0: # this regex looks for a number between 0-999
		if len(tempCardList) == 0:
			yield from client.send_message(message.channel, 'No card list to search. Generate a list of cards first.')
		else:
			input = re.findall(r"![0-9]{1,3}", message.content)
			number = input[0].split('!')
			if len(tempCardList) >= (int(number[1]) - 1): # list index starts at 0, card list starts at 1
				toSend = findCardsByName(tempCardList[int(number[1]) - 1])
				toSend = toSend[:toSend.rfind(',')]
				yield from client.send_message(message.channel, toSend)
	
	# a user uses this if a list of cards exceeds 25 results. This is used to paginate lists of cards to keep spam down
	elif message.content.startswith('!cont'):
		if(len(tempCardList) > 25):
			toSend = nextPage()
			toSend = toSend[:toSend.rfind(',')]
			yield from client.send_message(message.channel, toSend)						
				

# takes a mandatory search parameter and an optional set code. Returns a string that represents a single cards data, a list of cards that match the search term or in the case where we search a partial term but only return one result, it returns a string such as 'Single match|Doom Blade|M10'. This is parsed above and reruns the method with the parameters 'Doom Blade' and 'M10'. This is janky af and I should change it.
def findCardsByName(cardName, usersetcode=''):
	# Grab the Gatherer data using the user input card name
	cards = Card.where(name='"%s"' % cardName).all()			
	
	global tempCardFlip # we need to use the global keyword to allow changes to the global variable to take place inside this function. Python does not necessarily use pass by value or reference. All variables are technically just pointers to values. Specifying the global keyword keeps the pointer consistent so that we can make appropriate value changes without changing where the pointer is pointing to. (I think)
	tempCardFlip = ''
	
	# if the card was found, grab price and image data
	if len(cards) > 0:
		
		index=-1 # this is weird. Python treats lists as cyclical. By default we will set the list index to -1. This will get us the last value in the list, even if the list only has one thing in it. This way we are by default always retrieving the newest print of a card.
		
		if usersetcode: # if the user specifies a set code, they want to see an older printing of a card. We iterate through each card in the results, find the index of the set code the user wants and set the list index to the same value
			for card in range(0,len(cards)):
				if usersetcode == cards[card].set:
					index = int(card)
					break
		
		
		# empty if no flip, set if flip
		cardFlipMessage = ''
		
		if cards[index].names and len(cards[index].names) > 1: # 'names' is only set if there are more than one related card (in the context of flips or melds)
			cardFlipMessage = '\r\nThis card has a reverse side. Type !flip to see it.'
			
			for card in range(0,len(cards[index].names)): # This may or may not be broken
				if cards[index].names[card] != cardName:
					tempCardFlip = cards[index].names[card]
					break
		
		# MTG Goldfish data							
		mtgoname = (cards[index].name).replace(' ', '+').replace('\'', '').replace(',', '').replace(':', '').replace('.', '') # remove special characters to ensure the link resolves
		mtgoset = (cards[index].set_name).replace(' ', '+').replace('\'', '').replace(',', '').replace(':', '').replace('.', '')			
		r = requests.get('https://www.mtggoldfish.com/price/%s/%s#online' % (mtgoset, mtgoname), timeout=10.000) # use the python requests library to retrieve and parse an html response
		soup = BeautifulSoup(r.text, 'html.parser') # delicious beautiful soup, an extremely useful and strong text parser				
		onlinepricelist = soup.findAll('div', class_="price-box online") # parse the html for all elements of tag div with specified class attribute
		paperpricelist = soup.findAll('div', class_="price-box paper")			
		onlineprice = 'None' # not all cards have both an online and physical price. Some are online only, some are physical only. Set None as default and modify if we find a price
		paperprice = 'None'
		
		if (len(onlinepricelist) > 0):			
			onlineprice = onlinepricelist[0].find('div', class_="price-box-price").contents[0]
			
		if (len(paperpricelist) > 0):
			paperprice = paperpricelist[0].find('div', class_="price-box-price").contents[0]
			
		# same MTG Goldfish workflow, but for foil prices
		r = requests.get('https://www.mtggoldfish.com/price/%s:Foil/%s#online' % (mtgoset, mtgoname), timeout=10.000)
		soup = BeautifulSoup(r.text, 'html.parser')				
		foilonlinepricelist = soup.findAll('div', class_="price-box online")
		foilpaperpricelist = soup.findAll('div', class_="price-box paper")			
		foilonlineprice = 'None'
		foilpaperprice = 'None'
		
		if (len(foilonlinepricelist) > 0):			
			foilonlineprice = foilonlinepricelist[0].find('div', class_="price-box-price").contents[0]			
			
		if (len(foilpaperpricelist) > 0):
			foilpaperprice = foilpaperpricelist[0].find('div', class_="price-box-price").contents[0]
		
		# set the image url to the card at the set code index, or most recent if none specified NOTE: this may not always return an image in the case of a missing multiverseid
		imageurl = cards[index].image_url				
				
		# empty if the card does not exists in multiple sets, set otherwise
		setMessage = ''				
			
		if len(cards) > 1 and cards[index].rarity != 'Basic Land': # lands are in all sets. If we look for all the sets lands are in the bot commits suicide
			setMessage = '\r\nThis card appears in the following sets: '
			for card in range(0,len(cards)):
				setMessage = setMessage + cards[card].set_name + '(' + cards[card].set +'), '
				
		return '<http://gatherer.wizards.com/Pages/Card/Details.aspx?multiverseid=%s>\r\n<https://www.mtggoldfish.com/price/%s/%s#online>\r\n%s\r\nReg: MTGO: %s || Paper: %s\r\nFoil: MTGO: %s || Paper: %s%s%s' % (cards[0].multiverse_id, mtgoset, mtgoname, imageurl, onlineprice, paperprice, foilonlineprice, foilpaperprice, setMessage, cardFlipMessage)
	
	# we did not find one specific card, so we are going to search for all cards that match the search term, if any
	else:
		r = requests.get('http://gatherer.wizards.com/Pages/Search/Default.aspx?name=+%%5B%s%%5D' % cardName, timeout=10.000) # search gatherer with the search term. NOTE: gatherer only returns 100 cards per page. If we match on more than 100 cards, the remaining cards are displayed in a new response. We currently don't handle this, but maybe we can in the future
		soup = BeautifulSoup(r.text, 'html.parser') # yum soup		
		cardsearch = soup.findAll('span', class_="cardTitle")																
		
		# did we find some?
		if len(cardsearch) > 0:	
			
			global tempCardList
			tempCardList = []
			
			for card in range(0,len(cardsearch)):
				tempCardList.append(cardsearch[card].find('a').contents[0])
														
			searchmessage = 'Your search found ' + str(len(tempCardList)) + ' cards: '
			
			count = 0 # show only 25 cards at a time and force the user to use !cont to retrieve the next paginated list of results							
			for card in range(0,len(tempCardList)):
				count = count + 1
				if count > 25:	
					global itemsShown
					itemsShown = 25
					searchmessage = searchmessage + '.\r\n\r\nType !cont to receive the next 25.'						
					break
				else:						
					searchmessage = searchmessage + tempCardList[card] + '(' + str(card+1) + '), '							
				
			return searchmessage			
			
		# this gets hit in the case that we either find no cards at all or we find one card and we are immediately taken to the card page rather than the search page
		else:
			multisearch = soup.findAll('span', {'id':'ctl00_ctl00_ctl00_MainContent_SubContent_SubContentHeader_subtitleDisplay'}) # this is gross, but necessary		
			if (len(multisearch) > 0):		
				return 'Single match found|%s|%s' % (multisearch[0].contents[0], usersetcode) # return our dreaded internal only string for parsing and rerun the function
			else:					
				return 'Search yielded no results.'	

# use the mtgsdk built in generate_booster function. This only kinda works because mtgsdk might be broken
def openBooster(setName):
	cards = Set.generate_booster(setName)	
			
	if(len(cards) > 0):
		
		global tempCardList
		tempCardList = []
		
		print(str(len(cards)))
		
		boosterMessage = 'You opened: '
		
		for card in range(0,len(cards)):
			tempCardList.append(cards[card].name)
			if random.randint(0,90) == 1:
				boosterMessage = boosterMessage + '%s(Foil %s)(%s), ' % (cards[card].name, cards[card].rarity, card + 1)
			else:
				boosterMessage = boosterMessage + '%s(%s)(%s), ' % (cards[card].name, cards[card].rarity, card + 1)
			
		return boosterMessage		
		
	else:
		return 'Incorrect set code.'

# here we go
def advancedSearch(query):
	# a huge ass list of card potential card properties, some can be lists
	# , represents AND, | represents OR in a list
	
	layoutp = ''            # one or list of: normal, split, flip, double-faced, token, plane, scheme, phenomenon, leveler, vanguard
	cmcp = '-1'             # one but may use operators (gt, gte, lt, lte)
	colorsp = ''            # one or list of: red, blue, white, black, green, (colorless?)
	colorIdentityp = ''     # one or list of: R,U,W,B,G,(C?)
	typep = ''              # one or list... too mant to list here
	supertypesp = ''        # one or list... too many to list here
	typesp = ''             # one or list
	subtypesp = ''          # one or list
	rarityp = ''            # one or list of: common, uncommon, rare, (mythic?), special, (land?)
	setp = ''		        # one or list (this is set code, not full name)
	setNamep = ''           # one or list (full name)
	textp = ''              # one or list !!!
	flavorp = ''            # one or list !!!
	artistp = ''            # one or list
	# numberp = ''          # one or list (this is a tiny ass number in the card bottom center)
	powerp = ''             # one but may use operators (gt, lt, gte, lte)
	toughnessp = ''         # one but may use operators
	loyaltyp = ''           # one but may use operators
	# foreignNamep = ''     # one
	# languagep = ''        # one
	gameFormatp = ''        # one
	legalityp = ''          # one
	orderbyp = ''           # one
	# containsp = ''        # one or list of card properties (like image_url)
		
	global tempCardList
	tempCardList = []
	
	cards = ['']
	
	
	properties = query.split(';')
	
	# in the future I can likely use a Dictionary of keys and values instead of this gross thing
	for prop in properties:
		if 'layout=' in prop:
			layoutp = prop.split('=')[1]				
		elif 'cmc=' in prop:
			cmcp = prop.split('=')[1]
		elif 'colors=' in prop:
			colorsp = prop.split('=')[1]
		elif 'colorIdentity=' in prop:
			colorIdentityp = prop.split('=')[1]
		elif 'type=' in prop:
			typep = prop.split('=')[1]
		elif 'supertypes=' in prop:
			supertypesp = prop.split('=')[1]
		elif 'types=' in prop:
			typesp = prop.split('=')[1]
		elif 'subtypes=' in prop:
			subtypesp = prop.split('=')[1]
		elif 'rarity=' in prop:
			rarityp = prop.split('=')[1]
		elif 'set=' in prop:
			setp = prop.split('=')[1]
		elif 'setName=' in prop:
			setNamep = prop.split('=')[1]
		elif 'text=' in prop:
			textp = prop.split('=')[1]
		elif 'flavor=' in prop:
			flavorp = prop.split('=')[1]
		elif 'artist=' in prop:
			artistp = prop.split('=')[1]
		# elif 'number=' in prop:
			# numberp = prop.split('=')[1]
		elif 'power=' in prop:
			powerp = prop.split('=')[1]
		elif 'toughness=' in prop:
			toughnessp = prop.split('=')[1]
		elif 'loyalty=' in prop:
			loyaltyp = prop.split('=')[1]
		# elif 'foreignName=' in prop:
			# foreignNamep = prop.split('=')[1]
		# elif 'language=' in prop:
			# languagep = prop.split('=')[1]
		elif 'gameFormat=' in prop:
			gameFormatp = prop.split('=')[1]
		elif 'legality=' in prop:
			legalityp = prop.split('=')[1]
		elif 'orderby=' in prop:
			orderbyp = prop.split('=')[1]
		# elif 'contains=' in prop:
			# containsp = prop.split('=')[1]
		
	# do the search!
	cards = Card.where(layout=layoutp) \
				.where(cmc=(cmcp if cmcp != '-1' else 'gte0')) \
				.where(colors=colorsp) \
				.where(colorIdentity=colorIdentityp) \
				.where(type=typep) \
				.where(supertypes=supertypesp) \
				.where(types=typesp) \
				.where(subtypes=subtypesp) \
				.where(rarity=rarityp) \
				.where(set=setp) \
				.where(setName=setNamep) \
				.where(text=textp) \
				.where(flavor=flavorp) \
				.where(artist=artistp) \
				.where(power=powerp) \
				.where(toughness=toughnessp) \
				.where(loyalty=loyaltyp) \
				.where(gameFormat=gameFormatp) \
				.where(legality=legalityp) \
				.where(orderBy=orderbyp) \
				.all()					

				# .where(number=numberp) \
				# .where(foreignName=foreignNamep) \
				# .where(language=languagep) \
				# .where(contains=containsp) \
	
	if(len(cards) > 0):					
		
		for card in range(0,len(cards)):
			tempCardList.append(cards[card].name)
		
		cardMessage = 'Your search found ' + str(len(tempCardList)) + ' cards: '
		count = 0
		
		for card in range(0,len(tempCardList)):			
			count = count + 1
			if count > 25:
				global itemsShown
				itemsShown = 25				
				cardMessage = cardMessage + '.\r\n\r\nType !cont to receive the next 25.'								
				break
			else:				
				cardMessage = cardMessage + tempCardList[card] + '(' + str(card+1) + '), '
		
		return cardMessage
	else:
		return 'Search yielded no results.'
		

def nextPage():
	cardMessage = 'Your search found ' + str(len(tempCardList)) + ' cards: '
	
	global itemsShown	
	count = 0
		
	for card in range(itemsShown,len(tempCardList)):		
		count = count + 1
		if count > 25:			
			cardMessage = cardMessage + '.\r\n\r\nType !cont to receive the next 25.'
			itemsShown = itemsShown + 25 # increase the results we've shown so we can keep track of what page we are on
			break
		else:				
			cardMessage = cardMessage + tempCardList[card] + '(' + str(card+1) + '), '					
	
	return cardMessage
	
config = SafeConfigParser()
config.read('config.ini') # meant to be in the same directory as mtg.py
# options = config.options('Discord') # find all options in the Discord section of the config.ini
secrettoken = config.get('Discord', 'SecretToken')

# now that we've defined the connection info and the methods the bot will use... connect and live! Secret token is used here that Discord generates. When commiting to source control - REMOVE THIS TOKEN, IT'S A SECRET		
client.run(secrettoken)