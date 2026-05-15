from django.shortcuts import render, redirect, get_object_or_404
from .models import Product, Cart, Order
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, LoginForm
from django.contrib import messages
import stripe
from django.conf import settings
from django.urls import reverse
stripe.api_key=settings.STRIPE_SECRET_KEY

def home(request):
    products = Product.objects.all()
    return render(request, 'home.html', {'products': products})


def products(request):
    items = Product.objects.all()
    return render(request, 'products.html', {'items': items})

def search(request):
    query = request.GET.get('q')
    items = Product.objects.all()

    if query:
        items = items.filter(name__icontains=query)

    return render(request, 'products.html', {
        'items': items,
        'query': query
    })

def product_detail(request, id):
    product = get_object_or_404(Product, id=id)
    return render(request, 'product_detail.html', {'product': product})


@login_required
def add_to_cart(request, id):
    product = get_object_or_404(Product, id=id)

    cart_item, created = Cart.objects.get_or_create(
        user=request.user,
        product=product
    )

    if not created:
        cart_item.quantity += 1
        cart_item.save()

    return redirect('cart')



@login_required
def cart(request):
    items = Cart.objects.filter(user=request.user)

    if request.method == "POST":

        if 'delete_item' in request.POST:
            item_id = request.POST.get('delete_item')
            Cart.objects.filter(id=item_id, user=request.user).delete()
            return redirect('cart')

        if 'increase_qty' in request.POST:
            item_id = request.POST.get('increase_qty')
            item = Cart.objects.get(id=item_id, user=request.user)
            item.quantity += 1
            item.save()
            return redirect('cart')

        if 'decrease_qty' in request.POST:
            item_id = request.POST.get('decrease_qty')
            item = Cart.objects.get(id=item_id, user=request.user)

            if item.quantity > 1:
                item.quantity -= 1
                item.save()
            else:
                item.delete()

            return redirect('cart')

        # ONLY SELECTED ITEMS
        if 'place_order' in request.POST:
            selected_ids = request.POST.getlist('selected_items')

            if selected_ids:
                request.session['selected_cart_items'] = selected_ids
                return redirect('checkout')

    # totals
    for item in items:
        item.total = item.product.price * item.quantity

    total_price = sum(item.total for item in items)

    return render(request, 'cart.html', {
        'items': items,
        'total_price': total_price
    })

@login_required
def place_order(request):
    return redirect('address')


@login_required
def checkout(request):
    selected_ids = request.session.get('selected_cart_items', [])
    cart_items = Cart.objects.filter(id__in=selected_ids, user=request.user)

    if not cart_items.exists():
        return redirect('cart')  # safety

    if request.method == "POST":
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        address = request.POST.get('address')

        request.session['name'] = name
        request.session['email'] = email
        request.session['phone'] = phone
        request.session['address'] = address

        method = request.POST.get('payment_method')

        #  COD
        if method == "cod":
            for item in cart_items:
                Order.objects.create(
                    user=request.user,
                    product=item.product,
                    quantity=item.quantity
                )

            cart_items.delete()

            # clear session
            request.session.pop('selected_cart_items', None)

            return redirect('success')

        # STRIPE
        elif method == "stripe":
            line_items = []

            for item in cart_items:
                line_items.append({
                    'price_data': {
                        'currency': 'inr',
                        'product_data': {
                            'name': item.product.name,
                        },
                        'unit_amount': int(item.product.price * 100),
                    },
                    'quantity': item.quantity,
                })

            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url='https://ecommerce-vivo-clone-2.onrender.com/success/',
                cancel_url='https://ecommerce-vivo-clone-2.onrender.com/checkout/',
            )

            return redirect(session.url)

    return render(request, 'checkout.html', {'cart_items': cart_items})

@login_required
def orders(request):
    orders = Order.objects.filter(user=request.user).order_by('-ordered_at')
    return render(request, 'orders.html', {'orders': orders})


@login_required
def success(request):
    selected_ids = request.session.get('selected_cart_items', [])

    cart_items = Cart.objects.filter(id__in=selected_ids, user=request.user)

    if cart_items.exists():
        for item in cart_items:
            Order.objects.create(
                user=request.user,
                product=item.product,
                quantity=item.quantity
            )

        cart_items.delete()

    # ✅ clear session after success
    request.session.pop('selected_cart_items', None)

    return render(request, 'success.html')


# Registration View
def register(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            confirm_password = request.POST.get('confirm_password')

            #  Check password match
            if password != confirm_password:
                messages.error(request, "Passwords do not match")
                return render(request, 'register.html', {'form': form})

            #  Check username/email existence
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already taken")
                return render(request, 'register.html', {'form': form})
            if User.objects.filter(email=email).exists():
                messages.error(request, "Email already registered")
                return render(request, 'register.html', {'form': form})

            # Create user
            user = User.objects.create_user(username=username, email=email, password=password)
            messages.success(request, "Registration successful! You can login now.")
            return redirect('login')
    else:
        form = RegisterForm()

    return render(request, 'register.html', {'form': form})


# Login View
def login(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            user = authenticate(request, username=username, password=password)
            if user:
                auth_login(request, user)
                return redirect('home')
            else:
                messages.error(request, "Invalid username or password")
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form})


# Logout View
def logout(request):
    auth_logout(request)
    return redirect('login')


